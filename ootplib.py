"""Reusable OOTP save parsing/editing core (no GUI, no globals).

Everything here was derived by reverse engineering and then confirmed against
the in-game Ratings Editor via controlled byte diffs on OOTP 27.
"""
import collections, os, re, struct

MAX_RATING = 200
NBLOCK = 18
SUPPORTED = {27}          # versions with a diff-confirmed layout

# Salary must stay inside the range the record locator validates against, or the
# coach becomes unfindable on the next run.
#
# Getting this number right took three attempts. 50,000 then 40,000 were each
# measured by scanning located records -- but locating a record *requires*
# passing this very test, so anyone paid less was invisible to the measurement
# that set it. A DSL hitting coach on $25,000 exposed the circularity.
# 25,000 is where it settles: it resolves every record that can be resolved,
# and lowering it further only invents anchors with non-round salaries
# ($21,405, $17,797) where the correct reading is "no contract".
SALARY_MIN = 25000
SALARY_MAX = 20000000
SALARY_STEP = 1000


# A nominal $1 salary is supported, but deliberately NOT accepted by the two
# primary locator passes: "01 00 00 00" is one of the commonest byte patterns in
# these records, and allowing it there moved 7022 of 10713 anchors. It is
# handled by a last-resort third pass that only runs when nothing else matches,
# which recovers $1 coaches exactly and provably cannot disturb anyone else.
SALARY_NOMINAL = 1


def salary_ok(v):
    """Salaries the record locator will trust (excludes the nominal $1)."""
    return v == 0 or (SALARY_MIN <= v <= SALARY_MAX and v % SALARY_STEP == 0)


def salary_valid(v):
    """Salaries that may be written or displayed, including nominal $1."""
    return v == SALARY_NOMINAL or salary_ok(v)

# rating block index -> Ratings Editor label
RATING_LABELS = {
    0: "Influences Mechanics", 1: "Handle Development", 2: "Handle Aging",
    9: "Scout Majors", 10: "Scout Minors",
    13: "Teach C", 14: "Teach IF", 15: "Teach OF",
    16: "Teach Hitting", 17: "Teach Pitching",
}
# The remaining 8 block slots are unidentified. They are NOT the six manager
# fields (Manager Personality / Positive+Negative Relation / Manager Style /
# Hitting+Pitching Coach Focus) -- those are categorical enums shown as
# "Normal", "Easygoing", "Smallball", "Neutral" and live elsewhere. Writing 200
# into any of these would be meaningless, so they are never touched.
UNKNOWN_SLOTS = [3, 4, 5, 6, 7, 8, 11, 12]

# "Teach Running" and "In-game Running" are the two remaining numeric ratings.
# They are NOT in the 18-byte block -- they sit at fixed offsets from the END of
# the record. Confirmed by in-game diff on coach 5473 (Starlyn Taveras):
# Teach Running 120->177 landed at end-38, In-game Running 96->133 at end-5.
TAIL_RATINGS = {38: "Teach Running", 5: "In-game Running"}

_NAME_RE = re.compile(rb"[A-Za-z .'\-\x80-\xff]{1,40}$")


def read_header(path):
    with open(path, "rb") as fh:
        h = fh.read(0x80)
    if h[1:5] != b"OOTP":
        raise ValueError("not an OOTP data file: %s" % path)
    return {"version": struct.unpack_from("<I", h, 5)[0],
            "name": h[0x19:0x26].split(b"\x00")[0].decode(),
            "count": struct.unpack_from("<I", h, 0x73)[0]}


def parse_names(path):
    """Return {id: name} for every name in the file.

    Entries are: tag(1) | len u32 | string | 4 zero bytes | id u32

    Two tag bytes carry names, 0x27 and 0x07. They are NOT "first names" and
    "surnames" in separate id spaces -- their id ranges are disjoint (1..264925
    and 31877..264948, zero overlap), so it is one shared id space split by some
    other attribute. Treating them as two tables meant a coach's surname was
    looked up in the wrong half whenever its id fell in the other tag's range,
    which blanked the surname for 3569 of 10713 coaches.
    """
    d = open(path, "rb").read()
    n = len(d)
    tables = []
    for tag in (0x27, 0x07):
        # The tag byte also occurs constantly as ordinary data, so collect every
        # candidate and then keep only the monotonically increasing id chain --
        # the real table is one long ascending run, false positives are not.
        cand = []
        i = -1
        while True:
            i = d.find(bytes([tag]), i + 1)
            if i < 0 or i + 9 > n:
                break
            ln = struct.unpack_from("<I", d, i + 1)[0]
            if not (1 <= ln <= 40) or i + 9 + ln > n:
                continue
            s = d[i + 5:i + 5 + ln]
            if not _NAME_RE.match(s) or d[i + 5 + ln:i + 9 + ln] != b"\0\0\0\0":
                continue
            nid = struct.unpack_from("<I", d, i + 9 + ln)[0]
            if nid:
                cand.append((nid, s))
        # Entries are stored in ascending id order, so walk the run and accept
        # each candidate whose id continues the sequence. This tolerates the
        # variable-length trailing block after each name and rejects the many
        # false positives (the tag byte also occurs as ordinary data).
        by_id = {}
        for nid, s in cand:
            by_id.setdefault(nid, s)
        out, nid = {}, 1
        while nid in by_id:
            out[nid] = by_id[nid].decode("latin1")
            nid += 1
        # pick up any later island the walk could not reach contiguously
        for nid2, s in by_id.items():
            out.setdefault(nid2, s.decode("latin1"))
        tables.append(out)
    merged = {}
    for t in tables:
        merged.update(t)
    return merged


def record_starts(d, count):
    """{coach_id: offset}. Birthdate (day,month,year LE32) sits at start+12 and
    coach ids increase monotonically, which together pin the record starts."""
    starts, last, n = {}, 0, len(d)
    for i in range(0, n - 6):
        if 1 <= d[i] <= 31 and 1 <= d[i + 1] <= 12:
            y = struct.unpack_from("<I", d, i + 2)[0]
            if 1935 <= y <= 2015 and d[i + 6] == 0:
                s = i - 12
                if s < 0:
                    continue
                cid = struct.unpack_from("<I", d, s)[0]
                if last < cid <= count:
                    starts[cid] = s
                    last = cid
    # recover ids the birth-year filter dropped, by scanning between neighbours
    missing = [k for k in range(1, count + 1) if k not in starts]
    i = 0
    while i < len(missing):
        j = i
        while j + 1 < len(missing) and missing[j + 1] == missing[j] + 1:
            j += 1
        run = missing[i:j + 1]
        lo, hi = starts.get(run[0] - 1), starts.get(run[-1] + 1)
        if lo is not None and hi is not None:
            for m in run:
                c = [p for p in range(lo + 1, hi - 4)
                     if struct.unpack_from("<I", d, p)[0] == m]
                if len(c) == 1:
                    starts[m] = c[0]
        i = j + 1
    for cid, s in starts.items():
        if struct.unpack_from("<I", d, s)[0] != cid:
            raise ValueError("offset for coach %d does not start that record" % cid)
    return starts


def _small(v):
    return v <= 10 or v >= 246


def _shape_ok(d, s, X, tail):
    if any(d[s + X + 10 + k] > MAX_RATING for k in range(NBLOCK)):
        return False
    return sum(_small(d[s + X + 28 + k]) for k in range(tail)) >= tail - 1


def anchors(d, s, e, lo=56, hi=160, tail=12):
    """Candidate offsets X of the contract preamble:

        X+0  u32 salary | X+4 u8 years | X+5 u32 ext salary | X+9 u8 ext years
        X+10 .. X+27    18 rating bytes (1..200)

    Strict pass = a well-formed real contract (correctly places coaches who
    have an extension). Coaches with no contract have an uninitialised
    preamble (MSVC 0xCD heap filler written to disk), so they only match the
    looser shape test.
    """
    hi = min(hi, e - s - 28 - tail)
    strict, loose = [], []
    for X in range(lo, hi):
        if not _shape_ok(d, s, X, tail):
            continue
        sal = struct.unpack_from("<I", d, s + X)[0]
        ext = struct.unpack_from("<I", d, s + X + 5)[0]
        ok_s = salary_ok(sal)
        ok_e = salary_ok(ext)
        if ok_s and ok_e and sal and d[s + X + 4] <= 15 and d[s + X + 9] <= 15:
            strict.append(X)
        if (sal == 0 or SALARY_MIN <= sal <= SALARY_MAX) \
                and struct.unpack_from("<I", d, s + X + 4)[0] <= 15 \
                and struct.unpack_from("<H", d, s + X + 8)[0] == 0:
            loose.append(X)
    if strict or loose:
        return strict or loose
    # last resort: a coach this tool set to a nominal $1
    nominal = []
    for X in range(lo, hi):
        if not _shape_ok(d, s, X, tail):
            continue
        if struct.unpack_from("<I", d, s + X)[0] != SALARY_NOMINAL:
            continue
        if struct.unpack_from("<I", d, s + X + 5)[0] not in (0, SALARY_NOMINAL):
            continue
        if d[s + X + 4] > 15 or d[s + X + 9] > 15:
            continue
        nominal.append(X)
    return nominal


class Coaches:
    def __init__(self, lg_dir, progress=None):
        self.dir = lg_dir
        self.path = os.path.join(lg_dir, "coaches.dat")
        self.hdr = read_header(self.path)
        self.d = bytearray(open(self.path, "rb").read())
        if progress:
            progress("locating %d coach records" % self.hdr["count"])
        self.starts = record_starts(self.d, self.hdr["count"])
        self.sorted_starts = sorted(self.starts.values())
        self._anchor = {}
        self._clubs = None
        self._torg = None
        if progress:
            progress("reading teams")
        self.tnames = teams_from_dat(lg_dir)
        self.team_ids = set(self.tnames)
        npath = os.path.join(lg_dir, "names.dat")
        if progress:
            progress("reading names")
        self.names = parse_names(npath) if os.path.exists(npath) else {}

    # --- field accessors -------------------------------------------------
    def u32(self, cid, off):
        return struct.unpack_from("<I", self.d, self.starts[cid] + off)[0]

    # The record holds a CHAIN of team ids starting at +58, terminated by the
    # 0xCB (203) marker: the coach's own team, then intermediate affiliates,
    # then the parent MLB club. For big-league staff the first two entries are
    # both the MLB club, which is why reading +62 alone appeared to work -- but
    # for minor-league staff the parent sits further along, and reading +62 gave
    # a sibling affiliate instead (e.g. a Palm Beach coach reporting "org 104").
    CHAIN = (58, 62, 66, 70, 74, 78)

    def team(self, cid):
        return self.u32(cid, 58)

    def employed(self, cid):
        """Unemployed coaches have no team fields at all, so +58 holds whatever
        follows -- often a stray 1, which used to be read as 'Arizona'. A real
        assignment always has BOTH of the first two chain slots as valid team
        ids ("26 26", "104 81"); a free agent looks like "1 <garbage>"."""
        return (self.u32(cid, 58) in self.team_ids
                and self.u32(cid, 62) in self.team_ids)

    def _parent_clubs(self):
        """Ids that act as an organization: a club is its own parent, so some
        employed coach has chain[0] == chain[1] == that id. Derived from the
        save rather than assuming 'ids 1..30 are MLB'."""
        if getattr(self, "_clubs", None) is None:
            clubs = set()
            for cid in self.starts:
                if not self.employed(cid):
                    continue
                # Top-level staff look like "26 26 <marker>" -- the club listed
                # twice and the chain ending immediately. Requiring the marker
                # matters: without it, affiliates whose records merely repeat an
                # id get promoted to organizations of their own.
                a, b = self.u32(cid, 58), self.u32(cid, 62)
                if a == b and self.u32(cid, 66) == 203:
                    clubs.add(a)
            self._clubs = clubs
        return self._clubs

    # A literal 1 appears in the chain of most minor-league coaches regardless of
    # affiliation (77 of Peoria's 115 coaches, though Peoria is a Cardinals farm
    # club), so it is a flag whose value collides with Arizona's team id. It is
    # ignored when voting and only used as a last-resort fallback.
    SENTINEL = 1

    def _chain_org(self, cid, skip_sentinel=True):
        """Parent club suggested by this coach's own record, or 0."""
        if not self.employed(cid):
            return 0
        clubs = self._parent_clubs()
        for o in self.CHAIN[1:]:
            v = self.u32(cid, o)
            # The chain is a contiguous run of team ids; stop at the marker or
            # at the first non-team value.
            if v == 203 or v not in self.team_ids:
                break
            if v == self.SENTINEL and skip_sentinel:
                continue
            if v in clubs:
                return v
        return 0

    def _team_org_map_UNUSED(self):
        """team id -> parent club, decided by majority vote of that team's coaches.

        Individual records are not trustworthy on their own: for some the field
        layout shifts and a stray 1 lands where the org belongs, which reads as
        "Arizona" (club id 1 is both a real team and the commonest small integer
        in these records). Teams have many coaches, so the correct parent wins
        the vote and the malformed records are outvoted.
        """
        if getattr(self, "_torg", None) is None:
            clubs = self._parent_clubs()
            votes, fallback = {}, {}
            for cid in self.starts:
                if not self.employed(cid):
                    continue
                t = self.team(cid)
                o = self._chain_org(cid)
                if o:
                    votes.setdefault(t, collections.Counter())[o] += 1
                elif self._chain_org(cid, skip_sentinel=False) == self.SENTINEL:
                    fallback[t] = self.SENTINEL
            out = {}
            for t in set(list(votes) + list(fallback) + list(clubs)):
                if t in clubs:
                    out[t] = t          # a club is its own organization
                elif t in votes:
                    out[t] = votes[t].most_common(1)[0][0]
                elif t in fallback:
                    out[t] = fallback[t]
            self._torg = out
        return self._torg

    def org(self, cid):
        """Parent club, read from this coach's own record.

        Heuristic, and deliberately kept simple. Two cleverer schemes were tried
        and both made things worse: a per-team majority vote sent Clearwater to
        Arizona (the sentinel 1 outvotes the real parent), and excluding the
        sentinel then mis-assigned whole teams (Arizona's own ACL club landed on
        the Cubs). This version is correct for every coach spot-checked against
        the game, but it over-includes org 1 because that id doubles as a flag.
        Use the Team filter when you need precision -- team (+58) is reliable.
        """
        if not self.employed(cid):
            return 0
        clubs = self._parent_clubs()
        for o in self.CHAIN:
            v = self.u32(cid, o)
            if v == 203 or v not in self.team_ids:
                break
            if v in clubs:
                return v
        return 0

    def name(self, cid):
        f = self.names.get(self.u32(cid, 4), "")
        l = self.names.get(self.u32(cid, 8), "")
        return ("%s %s" % (f, l)).strip() or "Coach #%d" % cid

    def rating_off(self, cid):
        if cid in self._anchor:
            return self._anchor[cid]
        s = self.starts[cid]
        import bisect
        j = bisect.bisect_right(self.sorted_starts, s)
        e = self.sorted_starts[j] if j < len(self.sorted_starts) else len(self.d)
        # X varies far more than first assumed (56..~110 observed), so search
        # wide and let the contract decide rather than the window: a coach with
        # a real salary is pinned by the strict test wherever it sits. Only
        # unsigned coaches, whose preamble is zeros/filler, fall back to shape.
        a = anchors(self.d, s, e)
        r = s + min(a) + 10 if a else None
        self._anchor[cid] = r
        return r

    def ratings(self, cid):
        r = self.rating_off(cid)
        return [self.d[r + k] for k in range(NBLOCK)] if r else None

    def record_end(self, cid):
        import bisect
        j = bisect.bisect_right(self.sorted_starts, self.starts[cid])
        return self.sorted_starts[j] if j < len(self.sorted_starts) else len(self.d)

    def tail_offsets(self, cid):
        """{offset_in_file: label} for the two end-anchored ratings, or {} if
        this record does not have the expected trailer."""
        e = self.record_end(cid)
        if e - self.starts[cid] < 64:
            return {}
        # every well-formed record ends with two zero bytes
        if self.d[e - 1] or self.d[e - 2]:
            return {}
        out = {}
        for back, label in TAIL_RATINGS.items():
            o = e - back
            if o <= self.starts[cid] or not (1 <= self.d[o] <= MAX_RATING):
                return {}
            out[o] = label
        return out

    def tail_ratings(self, cid):
        return {lbl: self.d[o] for o, lbl in self.tail_offsets(cid).items()}

    def contract(self, cid):
        r = self.rating_off(cid)
        if r is None:
            return None
        o = r - 10
        sal = struct.unpack_from("<I", self.d, o)[0]
        real = salary_valid(sal)
        return {"salary": sal if real else 0, "years": self.d[o + 4],
                "ext_salary": struct.unpack_from("<I", self.d, o + 5)[0] if real else 0,
                "ext_years": self.d[o + 9], "real": real}

    # --- edits -----------------------------------------------------------
    def average_salary(self, org=None):
        """Mean salary over coaches holding a real contract, rounded to $1000.
        Pass an org id to average that organization only."""
        vals = []
        for cid in self.starts:
            if org is not None and self.org(cid) != org:
                continue
            c = self.contract(cid)
            if c and c["salary"] > 0:
                vals.append(c["salary"])
        if not vals:
            return 0
        return int(round(sum(vals) / len(vals) / SALARY_STEP) * SALARY_STEP)

    def apply(self, cid, max_ratings=True, indices=None, years=None,
              ext_years=None, include_unknown=False, salary=None):
        """Returns 'ok', 'no_contract' (ratings done, contract skipped),
        'partial' (only the end-anchored ratings could be written), or
        'unresolved' (nothing done)."""
        r = self.rating_off(cid)
        # The end-anchored ratings are independent of the block anchor, so write
        # them even when the block cannot be located.
        if max_ratings:
            for o in self.tail_offsets(cid):
                self.d[o] = MAX_RATING
        if r is None:
            return "partial" if (max_ratings and self.tail_offsets(cid)) else "unresolved"
        if max_ratings:
            idx = list(indices if indices is not None else RATING_LABELS)
            if include_unknown:
                idx += UNKNOWN_SLOTS
            for i in idx:
                self.d[r + i] = MAX_RATING
        if years is None and ext_years is None and salary is None:
            return "ok"
        o = r - 10
        sal = struct.unpack_from("<I", self.d, o)[0]
        if not (sal and salary_ok(sal)):
            # No contract on file: the preamble is uninitialised heap filler.
            # Writing a term here would (a) invent a contract the game never
            # generates and (b) make this record undetectable on the next run,
            # because the anchor is validated against these very fields.
            return "no_contract"
        if salary is not None:
            if not salary_valid(salary) or salary == 0:
                raise ValueError("salary must be $%d, or a multiple of $%d between "
                                 "$%d and $%d" % (SALARY_NOMINAL, SALARY_STEP,
                                                  SALARY_MIN, SALARY_MAX))
            struct.pack_into("<I", self.d, o, salary)
            # keep an existing extension in step with the new base salary
            if struct.unpack_from("<I", self.d, o + 5)[0]:
                struct.pack_into("<I", self.d, o + 5, salary)
            sal = salary
        if years is not None:
            self.d[o + 4] = years
        if ext_years is not None:
            self.d[o + 9] = ext_years
            # an extension term at $0/yr renders as a nonsense contract, so
            # mirror the base salary to keep the extension self-consistent
            if ext_years and not struct.unpack_from("<I", self.d, o + 5)[0]:
                struct.pack_into("<I", self.d, o + 5, sal)
        return "ok"

    def save(self, backup=True):
        if backup:
            b = self.path + ".bak"
            i = 1
            while os.path.exists(b):
                b = "%s.bak%d" % (self.path, i)
                i += 1
            with open(b, "wb") as fh:
                fh.write(open(self.path, "rb").read())
        if len(self.d) != os.path.getsize(self.path):
            raise RuntimeError("length changed - refusing to write")
        with open(self.path, "wb") as fh:
            fh.write(self.d)
        return True


def _lenstr(d, i, maxlen=48):
    """LE32 length + printable bytes, the string form OOTP uses throughout."""
    if i + 4 > len(d):
        return None
    n = struct.unpack_from("<I", d, i)[0]
    if not (1 <= n <= maxlen) or i + 4 + n > len(d):
        return None
    s = d[i + 4:i + 4 + n]
    if not re.fullmatch(rb"[ -~\x80-\xff]+", s):
        return None
    return s.decode("latin1"), i + 4 + n


def teams_from_dat(lg_dir):
    """id -> "City Nickname", read straight out of teams.dat.

    Each team carries four consecutive length-prefixed strings - city,
    abbreviation, nickname, logo filename - and the team id is the u32
    immediately before the city. Verified against the news-tag names on a
    mature save: 268/268 identical, plus 10 teams the news scan never saw.
    """
    path = os.path.join(lg_dir, "teams.dat")
    if not os.path.exists(path):
        return {}
    d = open(path, "rb").read()
    out, i, n = {}, 0, len(d)
    while i < n - 8:
        a = _lenstr(d, i)
        if a:
            city, j = a
            b = _lenstr(d, j, 6)
            if b:
                _abbr, k = b
                c = _lenstr(d, k)
                if c:
                    nick, m = c
                    e = _lenstr(d, m, 80)
                    if e and e[0].lower().endswith(".png") and i >= 4:
                        tid = struct.unpack_from("<I", d, i - 4)[0]
                        if 0 < tid < 10000 and tid not in out:
                            out[tid] = ("%s %s" % (city, nick)).strip()
                        i = e[1]
                        continue
        i += 1
    return out


def _cache_path(lg_dir):
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "OOTPCoachEditor")
    os.makedirs(d, exist_ok=True)
    key = re.sub(r"[^A-Za-z0-9]+", "_", lg_dir)[-80:]
    return os.path.join(d, key + ".teams.json")


def team_names(lg_dir, use_cache=True):
    """id -> display name.

    teams.dat is the real source: complete, fast, and present even in a
    brand-new save. The old approach scraped <Name:team#id> tags out of the
    news in messages/, which silently produced "Team #135" placeholders on a
    fresh game because no news had been generated yet. That scan is kept only
    as a fallback in case teams.dat cannot be parsed.
    """
    import json
    names = teams_from_dat(lg_dir)
    if names:
        return names
    pat = re.compile(rb"<([^<>]{1,45}):team#(\d{1,4})>")
    cp = _cache_path(lg_dir)
    if use_cache and os.path.exists(cp):
        try:
            return {int(k): v for k, v in json.load(open(cp)).items()}
        except Exception:
            pass
    out = {}
    for sub in ("messages", "."):
        p = os.path.join(lg_dir, sub)
        if not os.path.isdir(p):
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [x for x in dirs if x not in ("auto-save", "temp")]
            for f in files:
                fp = os.path.join(root, f)
                try:
                    if os.path.getsize(fp) > 20_000_000:
                        continue
                    data = open(fp, "rb").read()
                except OSError:
                    continue
                for nm, i in pat.findall(data):
                    i = int(i)
                    nm = nm.decode("latin1")
                    if i not in out or len(nm) > len(out[i]):
                        out[i] = nm
        if out:
            break
    try:
        json.dump(out, open(cp, "w"))
    except Exception:
        pass
    return out


def find_saves(roots=None):
    """[(label, lg_dir, version)] for every save under the OOTP Documents dirs."""
    if roots is None:
        home = os.path.expanduser("~")
        roots = [os.path.join(home, "Documents", "Out of the Park Developments")]
    found = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for game in sorted(os.listdir(root)):
            sg = os.path.join(root, game, "saved_games")
            if not os.path.isdir(sg):
                continue
            for lg in sorted(os.listdir(sg)):
                p = os.path.join(sg, lg)
                if not lg.endswith(".lg") or not os.path.isdir(p):
                    continue
                cp = os.path.join(p, "coaches.dat")
                if not os.path.exists(cp):
                    continue
                try:
                    v = read_header(cp)["version"]
                except Exception:
                    continue
                found.append(("%s - %s" % (game, lg[:-3]), p, v))
    return found
