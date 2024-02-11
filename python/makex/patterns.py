import re
from typing import Pattern


def make_glob_pattern(pat: str) -> str:
    """Translate a shell PATTERN to a regular expression.

    Derived from `fnmatch.translate()` of Python version 3.8.13
    SOURCE: https://github.com/python/cpython/blob/v3.8.13/Lib/fnmatch.py#L74-L128
    SOURCE: https://stackoverflow.com/a/72400344
    """

    i, n = 0, len(pat)
    res = ''
    while i < n:
        c = pat[i]
        i = i + 1
        if c == '*':
            # -------- CHANGE START --------
            # prevent '*' matching directory boundaries, but allow '**' to match them
            j = i
            if j < n and pat[j] == '*':
                res = res + '.*'
                i = j + 1
            else:
                res = res + '[^/]*'
            # -------- CHANGE END ----------
        elif c == '?':
            # -------- CHANGE START --------
            # prevent '?' matching directory boundaries
            res = res + '[^/]'
            # -------- CHANGE END ----------
        elif c == '[':
            j = i
            if j < n and pat[j] == '!':
                j = j + 1
            if j < n and pat[j] == ']':
                j = j + 1
            while j < n and pat[j] != ']':
                j = j + 1
            if j >= n:
                res = res + '\\['
            else:
                stuff = pat[i:j]
                if '--' not in stuff:
                    stuff = stuff.replace('\\', r'\\')
                else:
                    chunks = []
                    k = i + 2 if pat[i] == '!' else i + 1
                    while True:
                        k = pat.find('-', k, j)
                        if k < 0:
                            break
                        chunks.append(pat[i:k])
                        i = k + 1
                        k = k + 3
                    chunks.append(pat[i:j])
                    # Escape backslashes and hyphens for set difference (--).
                    # Hyphens that create ranges shouldn't be escaped.
                    stuff = '-'.join(s.replace('\\', r'\\').replace('-', r'\-') for s in chunks)
                # Escape set operations (&&, ~~ and ||).
                stuff = re.sub(r'([&~|])', r'\\\1', stuff)
                i = j + 1
                if stuff[0] == '!':
                    # -------- CHANGE START --------
                    # ensure sequence negations don't match directory boundaries
                    stuff = '^/' + stuff[1:]
                    # -------- CHANGE END ----------
                elif stuff[0] in ('^', '['):
                    stuff = '\\' + stuff
                res = '%s[%s]' % (res, stuff)
        else:
            res = res + re.escape(c)
    return r'(?s:%s)\Z' % res


def combine_patterns(patterns: list[str], flags=re.X | re.U | re.DOTALL) -> Pattern:
    # combine patterns into one for faster evaluation
    # this will/should build a type of tree with lookaheads
    template = "(?={pattern})"
    new_pattern = []
    for pattern in patterns:
        new_pattern.append(template.format(pattern=pattern))

    pattern = "|".join(new_pattern)
    return re.compile(pattern, flags=flags)
