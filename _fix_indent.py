lines = open('main.py', encoding='utf-8').read().splitlines()
for i, l in enumerate(lines):
    if l.strip() == 'session_id = request.cookies.get("session_id")':
        nxt = lines[i + 1]
        lines[i + 1] = '    ' + nxt.strip()
        print('fixed line', i + 2, '->', lines[i + 1])
        break
open('main.py', 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
import py_compile
py_compile.compile('main.py', doraise=True)
print('main.py syntax OK')