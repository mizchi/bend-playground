import re,sys,pathlib
f,defs = sys.argv[1], sys.argv[2:]
p=pathlib.Path(f); s=p.read_text()
for d in defs:
    name,val = d.split('=')
    s=re.sub(r'(def %s\(\) -> Nat:\n  )\d+n' % re.escape(name), r'\g<1>%sn'%val, s)
p.write_text(s)
