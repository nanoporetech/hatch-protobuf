import importlib.resources
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List

import tomli_w

ROOT = Path(__file__).parent.parent

PROJECT_TEMPLATE = {
    "project": {
        "name": "test-project",
        "version": "0.0.1",
        "dependencies": [
            "grpcio",
            "protobuf",
        ],
    },
    "build-system": {
        "requires": [
            "hatchling",
            f"hatch-protobuf @ {ROOT.as_uri()}",
        ],
        "build-backend": "hatchling.build",
    },
}

GITIGNORE = """\
*_pb2.py
*_pb2.pyi
*_pb2_grpc.py
*_pb2_grpc.pyi
"""


COMMON_WHEEL_FILES = [
    "__init__.py",
    "helloworld.proto",
]


def create_root_project_files(path: Path, hook_settings: Dict[str, Any]) -> None:
    """Create a directory containing a pyproject.toml and a .gitignore."""
    path.mkdir(parents=True, exist_ok=True)
    settings = PROJECT_TEMPLATE | {
        "tool": {"hatch": {"build": {"hooks": {"protobuf": hook_settings}}}}
    }
    with (path / "pyproject.toml").open("wb") as f:
        tomli_w.dump(settings, f)
    print((path / "pyproject.toml").read_text())
    (path / ".gitignore").write_text(GITIGNORE)


def create_proto_dir_consumer(path: Path) -> None:
    """Create a directory containing the test consumer.proto."""
    path.mkdir(parents=True, exist_ok=True)
    proto = importlib.resources.read_text("tests", "consumer.proto")
    (path / "consumer.proto").write_text(proto)


def create_proto_dir(path: Path) -> None:
    """Create a directory containing the test helloworld.proto."""
    path.mkdir(parents=True, exist_ok=True)
    proto = importlib.resources.read_text("tests", "helloworld.proto")
    (path / "helloworld.proto").write_text(proto)


def create_module_dir(path: Path, with_proto: bool) -> None:
    """Create a directory containing __init__.py and (optionally) the test helloworld.proto."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "__init__.py").touch()
    if with_proto:
        create_proto_dir(path)


def build_wheel(
    project: Path, capture_output: bool = False, verbose: bool = False
) -> subprocess.CompletedProcess:
    """Run `hatch build` on the project."""
    args = [
        sys.executable,
        "-m",
        "hatch",
        "build",
        ".",
    ]
    if verbose:
        args.insert(3, "-v")
    return subprocess.run(
        args,
        cwd=project,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def open_wheel(project: Path) -> zipfile.ZipFile:
    """Find a previously-built wheel, and open it."""
    [wheel_path] = list(project.glob("**/*.whl"))
    return zipfile.ZipFile(wheel_path)


def get_module_dir(wheel: zipfile.ZipFile) -> zipfile.Path:
    """Get the test_project module in the wheel.

    Also checks that there are no stray top-level files in the wheel.
    """
    root = zipfile.Path(wheel)
    assert {p.name for p in root.iterdir()} == {
        "test_project",
        "test_project-0.0.1.dist-info",
    }
    return root / "test_project"


def get_imports(file: zipfile.Path) -> List[str]:
    """Parses a Python file for its top-level imports.

    This uses heuristics and may get it wrong, but it's good enough for the tests.
    """
    lines = file.read_text().splitlines()
    imports = []
    for line in lines:
        line = line.strip()
        if line.startswith('"') or line.startswith("#"):
            continue
        if line.startswith("def ") or line.startswith("class ") or " = " in line:
            # we've found the start of the actual code
            break

        words = line.split()
        try:
            if words[0] in ("from", "import"):
                imports.append(words[1])
        except IndexError:
            pass
    return imports


def test_basic_settings():
    """Check a project using default settings."""
    with tempfile.TemporaryDirectory() as project_dir_str:
        project_dir = Path(project_dir_str)

        create_root_project_files(project_dir, {})
        create_module_dir(project_dir / "test_project", with_proto=True)

        build_wheel(project_dir)
        with open_wheel(project_dir) as wheel:
            module_dir = get_module_dir(wheel)

            assert {p.name for p in module_dir.iterdir()} == {
                *COMMON_WHEEL_FILES,
                "helloworld_pb2.py",
                "helloworld_pb2.pyi",
                "helloworld_pb2_grpc.py",
            }


def test_no_grpc():
    """Check that turning off the generate_grpc option works."""
    with tempfile.TemporaryDirectory() as project_dir_str:
        project_dir = Path(project_dir_str)

        create_root_project_files(project_dir, {"generate_grpc": False})
        create_module_dir(project_dir / "test_project", with_proto=True)

        build_wheel(project_dir)
        with open_wheel(project_dir) as wheel:
            module_dir = get_module_dir(wheel)

            assert {p.name for p in module_dir.iterdir()} == {
                *COMMON_WHEEL_FILES,
                "helloworld_pb2.py",
                "helloworld_pb2.pyi",
            }


def test_no_pyi():
    """Check that turning off the generate_pyi option works."""
    with tempfile.TemporaryDirectory() as project_dir_str:
        project_dir = Path(project_dir_str)

        create_root_project_files(project_dir, {"generate_pyi": False})
        create_module_dir(project_dir / "test_project", with_proto=True)

        build_wheel(project_dir)
        with open_wheel(project_dir) as wheel:
            module_dir = get_module_dir(wheel)

            assert {p.name for p in module_dir.iterdir()} == {
                *COMMON_WHEEL_FILES,
                "helloworld_pb2.py",
                "helloworld_pb2_grpc.py",
            }


def test_custom_generator():
    """Check that configurating a custom generator works."""
    with tempfile.TemporaryDirectory() as project_dir_str:
        project_dir = Path(project_dir_str)

        create_root_project_files(
            project_dir,
            {
                "dependencies": ["mypy-protobuf~=3.0"],
                "generate_pyi": False,
                "generators": [
                    {
                        "name": "mypy",
                        "outputs": ["{proto_path}/{proto_name}_pb2.pyi"],
                    },
                    {
                        "name": "mypy_grpc",
                        "outputs": ["{proto_path}/{proto_name}_pb2_grpc.pyi"],
                    },
                ],
            },
        )
        create_module_dir(project_dir / "test_project", with_proto=True)

        build_wheel(project_dir)
        with open_wheel(project_dir) as wheel:
            module_dir = get_module_dir(wheel)

            assert {p.name for p in module_dir.iterdir()} == {
                *COMMON_WHEEL_FILES,
                "helloworld_pb2.py",
                "helloworld_pb2.pyi",
                "helloworld_pb2_grpc.py",
                "helloworld_pb2_grpc.pyi",
            }


def test_src_subdir():
    """Check that using a 'src' subdirectory works.

    Custom generators are also used to check they also respect the src subdir.
    """
    with tempfile.TemporaryDirectory() as project_dir_str:
        project_dir = Path(project_dir_str)

        create_root_project_files(
            project_dir,
            {
                "dependencies": ["mypy-protobuf~=3.0"],
                "generate_pyi": False,
                "generators": [
                    {
                        "name": "mypy",
                        "outputs": ["{proto_path}/{proto_name}_pb2.pyi"],
                    },
                    {
                        "name": "mypy_grpc",
                        "outputs": ["{proto_path}/{proto_name}_pb2_grpc.pyi"],
                    },
                ],
            },
        )
        create_module_dir(project_dir / "src" / "test_project", with_proto=True)

        build_wheel(project_dir)
        with open_wheel(project_dir) as wheel:
            module_dir = get_module_dir(wheel)

            assert {p.name for p in module_dir.iterdir()} == {
                *COMMON_WHEEL_FILES,
                "helloworld_pb2.py",
                "helloworld_pb2.pyi",
                "helloworld_pb2_grpc.py",
                "helloworld_pb2_grpc.pyi",
            }

            # It's easy to mess up the protoc command line so that protoc thinks the
            # module is "src.test_project" instead of just "test_project".
            for file in module_dir.iterdir():
                if file.name.endswith(".py") or file.name.endswith(".pyi"):
                    for imp in get_imports(file):
                        assert not imp.startswith(
                            "src."
                        ), f"{file.name}: {imp} starts with 'src.'"


def test_input_dir_different_from_output_dir():
    """Check that specifying different input and output directories works."""
    with tempfile.TemporaryDirectory() as project_dir_str:
        project_dir = Path(project_dir_str)

        create_root_project_files(
            project_dir,
            {
                "proto_paths": ["protos"],
                "output_path": "src",
            },
        )
        create_module_dir(project_dir / "src" / "test_project", with_proto=False)
        create_proto_dir(project_dir / "protos" / "test_project")

        build_wheel(project_dir)
        with open_wheel(project_dir) as wheel:
            module_dir = get_module_dir(wheel)

            assert {p.name for p in module_dir.iterdir()} == {
                "__init__.py",
                # NB: no .proto file!
                "helloworld_pb2.py",
                "helloworld_pb2.pyi",
                "helloworld_pb2_grpc.py",
            }


def test_bad_proto_paths():
    """Check that setting incorrect proto_paths produces a sensible error."""
    with tempfile.TemporaryDirectory() as project_dir_str:
        project_dir = Path(project_dir_str)

        create_root_project_files(
            project_dir,
            {
                # this should be a list!
                "proto_paths": "path/to/stuff",
                "output_path": "src",
            },
        )
        create_module_dir(project_dir / "test_project", with_proto=True)

        try:
            build_wheel(project_dir, capture_output=True)
            # we expect an exception
            assert False
        except subprocess.CalledProcessError as e:
            assert "proto_paths must be a list" in e.stderr


def test_external_paths():
    """Check that setting incorrect proto_paths produces a sensible error."""
    with tempfile.TemporaryDirectory() as temp_dir_str:
        parent_dir = Path(temp_dir_str)
        project_dir = parent_dir / "project"

        create_root_project_files(project_dir, {"proto_paths": ["../proto"]})
        create_module_dir(project_dir / "test_project", with_proto=False)
        create_proto_dir(parent_dir / "proto" / "test_project")

        build_wheel(project_dir)
        with open_wheel(project_dir) as wheel:
            module_dir = get_module_dir(wheel)

            assert {p.name for p in module_dir.iterdir()} == {
                "__init__.py",
                # NB: no .proto file!
                "helloworld_pb2.py",
                "helloworld_pb2.pyi",
                "helloworld_pb2_grpc.py",
            }


def test_library_paths():
    """Check that setting library_paths works."""
    with tempfile.TemporaryDirectory() as temp_dir_str:
        parent_dir = Path(temp_dir_str)
        project_dir = parent_dir / "project"

        create_root_project_files(
            project_dir,
            {
                "proto_paths": ["protos"],
                "library_paths": [str(Path("libs") / "lib1")],
                "output_path": "src",
            },
        )
        create_module_dir(project_dir / "src" / "test_project", with_proto=False)
        create_proto_dir_consumer(project_dir / "protos" / "test_project")
        create_proto_dir(project_dir / "libs" / "lib1" / "world")

        build_wheel(project_dir)
        with open_wheel(project_dir) as wheel:
            module_dir = get_module_dir(wheel)

            assert {p.name for p in module_dir.iterdir()} == {
                "__init__.py",
                # NB: no .proto file!
                "consumer_pb2.py",
                "consumer_pb2.pyi",
                "consumer_pb2_grpc.py",
            }


def test_custom_generator_with_options():
    """Check that the `options` parameter for custom generators is passed to protoc."""
    with tempfile.TemporaryDirectory() as project_dir_str:
        project_dir = Path(project_dir_str)

        create_root_project_files(
            project_dir,
            {
                "dependencies": ["mypy-protobuf~=3.0"],
                "generate_pyi": False,
                "generators": [
                    {
                        "name": "mypy",
                        "outputs": ["{proto_path}/{proto_name}_pb2.pyi"],
                        "options": ["foo=1", "bar=two"],
                    },
                ],
            },
        )
        create_module_dir(project_dir / "test_project", with_proto=True)

        result = build_wheel(project_dir, capture_output=True, verbose=True)
        assert "--mypy_opt=foo=1" in result.stderr
        assert "--mypy_opt=bar=two" in result.stderr
