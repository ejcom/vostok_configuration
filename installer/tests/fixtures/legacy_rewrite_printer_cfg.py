import sys, re
path, electronics, blocks_path = sys.argv[1:4]
text = open(path, encoding="utf-8").read().split("\n")
blocks = open(blocks_path, encoding="utf-8").read().rstrip("\n").split("\n")
hdr = re.compile(r"\s*(\[|#\*#)")
out, i, inserted, has_inc = [], 0, False, False
while i < len(text):
    line = text[i]
    if re.match(r"\s*\[mcu(\s+[^\]]+)?\]", line):
        # убрать секцию [mcu ...] целиком (до следующего заголовка или блока SAVE_CONFIG), вставить свои блоки на место первой
        if not inserted:
            out.extend(blocks + [""])
            inserted = True
        i += 1
        body = []
        while i < len(text) and not hdr.match(text[i]):
            body.append(text[i]); i += 1
        # комментарии прямо перед следующим заголовком относятся к нему, их оставляем
        keep = []
        while body and body[-1].lstrip().startswith("#"):
            keep.insert(0, body.pop())
        out.extend(keep)
        continue
    if re.match(r"\s*\[include\s+electronics_.*\.cfg\]", line):
        tail = line.split("]", 1)[1]
        line = "[include %s]%s" % (electronics, tail)
        has_inc = True
    out.append(line)
    i += 1
if not has_inc:
    for k, l in enumerate(out):
        if re.match(r"\s*\[include\s+printer_base\.cfg\]", l):
            out.insert(k + 1, "[include %s]" % electronics); break
if not inserted:
    out = blocks + [""] + out
open(path, "w", encoding="utf-8").write("\n".join(out))
