"""Every narration pulse of a lesson script, as (phrase, token ids, their text and bar), to compare two versions of
the engine. Run from rehearsal-tracks: python3 -m memorize.pulse_dump SCRIPT.py OUT.json"""
import sys, os, json, importlib.util


def main(path, out):
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    spec = importlib.util.spec_from_file_location('lesson_script', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    L = m.make()
    rows = [[p['text'], [[i, L.sh.tok[i]['text'], L.sh.tok[i]['bar'], bool(L.sh.tok[i].get('bold'))]
                         for i in p['pulse_ids']]] for s in L.segs for p in s.get('phrases', [])]
    json.dump(rows, open(out, 'w'), ensure_ascii=False, indent=0)
    print(len(rows), 'phrases;', sum(1 for r in rows for i in r[1] if not i[3]), 'pulsed tokens not bold')


if __name__ == '__main__':
    main(*sys.argv[1:3])
