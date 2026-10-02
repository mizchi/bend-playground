"""Deterministic application layouts and adversarial browser comparison inputs."""
import copy
import random


def dashboard():
    def panel(name, column, row, cs=1, rs=1, count=8):
        return {"id": name, "column": column, "row": row, "span_column": cs, "span_row": rs,
                "grid": {"columns": "repeat(4, minmax(0px, 1fr))", "rows": "32px 1fr", "gap": 8,
                         "auto_rows": "minmax(20px, 1fr)"},
                "children": [{"id": f"{name}-{i}", **({"span_column": 4} if i == 0 else {})}
                             for i in range(count)]}
    return {"id": "dashboard", "width": 1440, "height": 900,
            "grid": {"columns": "240px repeat(4, minmax(80px, 1fr))",
                     "rows": "64px repeat(3, minmax(80px, 1fr))", "gap": 12},
            "children": [panel("navigation", 1, 1, rs=4, count=17),
                         panel("toolbar", 2, 1, cs=4, count=5),
                         panel("chart", 2, 2, cs=3, rs=2, count=25),
                         panel("sales", 5, 2, count=9), panel("users", 5, 3, count=9),
                         panel("activity", 2, 4, cs=2, count=13),
                         panel("tasks", 4, 4, cs=2, count=13)]}


def cards(count=120, dense=True):
    return {"id": "catalog", "width": 1280, "height": 1800,
            "grid": {"columns": "repeat(6, minmax(100px, 1fr))", "gap": 12,
                     "auto_rows": "90px", "dense": dense},
            "children": [{"id": f"card-{i}", "span_column": 2 if i % 7 == 0 else 1,
                          "span_row": 2 if i % 11 == 0 else 1} for i in range(count)]}


def nested(depth=3, fanout=4):
    def node(path, level):
        if not level:
            return {"id": path}
        return {"id": path, "grid": {"columns": "repeat(2, minmax(0px, 1fr))",
                "rows": "repeat(2, minmax(0px, 1fr))", "gap": 2},
                "children": [node(f"{path}-{i}", level - 1) for i in range(fanout)]}
    return {**node("nested", depth), "width": 1200, "height": 900}


def browser_cases():
    cases = []
    for page in [dashboard(), cards(40), cards(40, False), nested()]:
        for width in [480, 1024, 1440]:
            cases.append({**copy.deepcopy(page), "width": width})
    # Empty grids, finite caps, fractional flex sums, zero tracks, overflow,
    # explicit overlap, fixed-row placement and implicit columns.
    for columns in ["0px 0fr minmax(90px, 0fr)", "0.25fr 0.5fr", "minmax(300px, 1fr) 3fr",
                    "minmax(20px, 80px) minmax(50px, 400px) 1fr", "repeat(32, 1fr)"]:
        for width in [120, 601]:
            cases.append({"id": "edge", "width": width, "height": 301,
                          "grid": {"columns": columns, "rows": "0.2fr minmax(200px, 1fr)", "gap": 3},
                          "children": [{"id": f"e{i}"} for i in range(8)]})
    cases.append({"id": "empty", "width": 500, "height": 500, "grid": {"columns": "1fr"}, "children": []})
    rng = random.Random(20261002)
    for i in range(80):
        cols = rng.randint(1, 8)
        tracks = rng.choices(["0.25fr", "1fr", "2fr", "90px", "minmax(80px, 1fr)",
                              "minmax(20px, 150px)"], k=cols)
        children = []
        for j in range(rng.randint(6, 20)):
            children.append({"id": f"r{i}-{j}", "span_column": rng.randint(1, 2),
                             "span_row": rng.randint(1, 3),
                             "column": rng.choice([0, 0, 0, 0, rng.randint(1, cols + 1)]),
                             "row": rng.choice([0, 0, 0, 0, rng.randint(1, 5)])})
        cases.append({"id": f"random-{i}", "width": rng.randint(300, 1400), "height": rng.randint(300, 900),
                      "grid": {"columns": " ".join(tracks), "rows": "minmax(60px, 1fr) 0.5fr",
                               "auto_columns": "minmax(40px, 1fr)", "auto_rows": "minmax(20px, 1fr)",
                               "column_gap": rng.randint(0, 16), "row_gap": rng.randint(0, 16),
                               "dense": bool(i % 2)}, "children": children})
    return cases
