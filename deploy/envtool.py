"""
Fill in a .env file without ever overwriting what's already there (deploy/setup.sh uses it, so running setup again
keeps your keys and settings).

  python3 envtool.py FILE KEY=VALUE ...   sets each KEY only if it's missing or empty
  python3 envtool.py FILE --force KEY=VALUE ...   sets each KEY whatever it was (setup does this once, on a new .env)
  python3 envtool.py FILE --empty KEY ... prints which of these keys are still empty (one per line)
  python3 envtool.py FILE --get KEY       prints KEY's value

Lines are kept in their order with their comments; a new key is added at the end.
"""
import sys
from pathlib import Path


def read(path):
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    vals = {}
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            vals[k.strip()] = (i, v.strip())
    return lines, vals


def main(argv):
    path, args = Path(argv[1]), argv[2:]
    lines, vals = read(path)
    if args and args[0] == "--empty":
        for k in args[1:]:
            if not vals.get(k, (0, ""))[1]:
                print(k)
        return
    if args and args[0] == "--get":
        print(vals.get(args[1], (0, ""))[1])
        return
    force = bool(args) and args[0] == "--force"
    for kv in args[1:] if force else args:
        k, v = kv.split("=", 1)
        if k in vals:
            i, old = vals[k]
            if force or not old:
                lines[i] = f"{k}={v}"
        else:
            lines.append(f"{k}={v}")
            vals[k] = (len(lines) - 1, v)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv)
