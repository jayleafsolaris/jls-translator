def entries_dict(lines):
    return {l[1]: l[2] for l in lines if l[0] == "entry"}
