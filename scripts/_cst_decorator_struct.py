import libcst as cst

src = """
class Dog:
    @classmethod
    def from_dict(cls, data: dict) -> 'Dog':
        return cls(data['name'])

    @staticmethod
    @some_other
    def helper() -> None:
        pass
"""

mod = cst.parse_module(src)
cls_node = mod.body[0]
print("ClassDef.decorators:", cls_node.decorators)
print()
for stmt in cls_node.body.body:
    if isinstance(stmt, cst.FunctionDef):
        print(f"FunctionDef({stmt.name.value}).decorators: {stmt.decorators}")
        for d in stmt.decorators:
            print(f"  Decorator type: {type(d).__name__}")
            print(f"  d.decorator: {d.decorator}")
        print(f"  FunctionDef children types: {[type(c).__name__ for c in stmt.children]}")
        print()
