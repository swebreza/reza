"""Tests for the graph parser module."""

import pytest
from pathlib import Path

from reza.graph.parser import (
    NodeInfo,
    EdgeInfo,
    detect_language,
    file_hash,
    parse_file,
    SUPPORTED_EXTENSIONS,
)


class TestDetectLanguage:
    def test_python(self):
        assert detect_language("foo.py") == "python"

    def test_javascript(self):
        assert detect_language("app.js") == "javascript"

    def test_typescript(self):
        assert detect_language("service.ts") == "typescript"

    def test_tsx(self):
        assert detect_language("component.tsx") == "tsx"

    def test_go(self):
        assert detect_language("main.go") == "go"

    def test_rust(self):
        assert detect_language("lib.rs") == "rust"

    def test_unsupported(self):
        assert detect_language("data.csv") is None

    def test_case_insensitive(self):
        assert detect_language("FOO.PY") == "python"


class TestFileHash:
    def test_hash_consistent(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("print('hello')\n")
        h1 = file_hash(str(f))
        h2 = file_hash(str(f))
        assert h1 == h2
        assert len(h1) == 64  # SHA-256

    def test_hash_changes(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("v1")
        h1 = file_hash(str(f))
        f.write_text("v2")
        h2 = file_hash(str(f))
        assert h1 != h2

    def test_missing_file(self):
        assert file_hash("/nonexistent/path.py") == ""


class TestParsePython:
    @pytest.fixture
    def py_file(self, tmp_path):
        f = tmp_path / "auth.py"
        f.write_text(
            'import os\n'
            'from pathlib import Path\n'
            '\n'
            'class AuthService:\n'
            '    def login(self, user, pwd):\n'
            '        result = validate(user)\n'
            '        return result\n'
            '\n'
            '    def logout(self):\n'
            '        pass\n'
            '\n'
            'def validate(user):\n'
            '    return os.getenv("SECRET")\n'
        )
        return str(f)

    def test_parses_nodes(self, py_file):
        nodes, edges, _ = parse_file(py_file)
        names = {n.name for n in nodes}
        assert "AuthService" in names
        assert "login" in names
        assert "logout" in names
        assert "validate" in names

    def test_parses_file_node(self, py_file):
        nodes, _, _ = parse_file(py_file)
        file_nodes = [n for n in nodes if n.kind == "File"]
        assert len(file_nodes) == 1
        assert file_nodes[0].language == "python"

    def test_parses_class(self, py_file):
        nodes, _, _ = parse_file(py_file)
        classes = [n for n in nodes if n.kind == "Class"]
        assert len(classes) == 1
        assert classes[0].name == "AuthService"

    def test_parses_functions(self, py_file):
        nodes, _, _ = parse_file(py_file)
        funcs = [n for n in nodes if n.kind == "Function"]
        assert len(funcs) >= 3  # login, logout, validate

    def test_contains_edges(self, py_file):
        _, edges, _ = parse_file(py_file)
        contains = [e for e in edges if e.kind == "CONTAINS"]
        assert len(contains) >= 3  # file->class, class->login, class->logout

    def test_import_edges(self, py_file):
        _, edges, _ = parse_file(py_file)
        imports = [e for e in edges if e.kind == "IMPORTS_FROM"]
        assert len(imports) >= 1
        targets = {e.target for e in imports}
        assert "os" in targets or "pathlib" in targets or "Path" in targets

    def test_call_edges(self, py_file):
        _, edges, _ = parse_file(py_file)
        calls = [e for e in edges if e.kind == "CALLS"]
        assert len(calls) >= 1
        call_targets = {e.target for e in calls}
        assert any("validate" in t for t in call_targets)


class TestParseTestFile:
    @pytest.fixture
    def test_file(self, tmp_path):
        f = tmp_path / "test_auth.py"
        f.write_text(
            'def test_login():\n'
            '    assert True\n'
            '\n'
            'def test_logout():\n'
            '    assert True\n'
        )
        return str(f)

    def test_detects_test_functions(self, test_file):
        nodes, _, _ = parse_file(test_file)
        tests = [n for n in nodes if n.is_test]
        assert len(tests) >= 2
        assert all(n.kind == "Test" for n in tests)

    def test_tested_by_edges(self, test_file):
        _, edges, _ = parse_file(test_file)
        tested_by = [e for e in edges if e.kind == "TESTED_BY"]
        assert len(tested_by) >= 2


class TestParseUnsupported:
    def test_unsupported_extension(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("a,b,c\n1,2,3\n")
        nodes, edges, _ = parse_file(str(f))
        assert nodes == []
        assert edges == []

    def test_missing_file(self):
        nodes, edges, _ = parse_file("/nonexistent/file.py")
        assert nodes == []
        assert edges == []


class TestParseInheritance:
    @pytest.fixture
    def inheritance_file(self, tmp_path):
        f = tmp_path / "models.py"
        f.write_text(
            'class BaseModel:\n'
            '    pass\n'
            '\n'
            'class UserModel(BaseModel):\n'
            '    def save(self):\n'
            '        pass\n'
        )
        return str(f)

    def test_inherits_edges(self, inheritance_file):
        _, edges, _ = parse_file(inheritance_file)
        inherits = [e for e in edges if e.kind == "INHERITS"]
        assert len(inherits) >= 1
        assert any("BaseModel" in e.target for e in inherits)
