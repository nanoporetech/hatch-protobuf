import importlib.resources
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from pathlib import Path
from typing import List

ROOT = Path(__file__).parent.parent

PYPROJECT_HEADER = """\
[project]
name = "test-project"
version = "0.0.1"
dependencies = ["grpcio", "protobuf"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

"""

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


def create_module_dir(path: Path) -> None:
    """Create a directory containing __init__.py and the test helloworld.proto."""
    path.mkdir(parents=True)
    (path / "__init__.py").touch()
    proto = importlib.resources.read_text("tests", "helloworld.proto")
    (path / "helloworld.proto").write_text(proto)


def build_wheel(project: Path) -> None:
    """Run `hatch build` on the project."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "hatch",
            "build",
            ".",
        ],
        cwd=project,
        check=True,
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

        with open(project_dir / "pyproject.toml", "w") as fobj:
            fobj.write(PYPROJECT_HEADER)
            fobj.write(
                textwrap.dedent(
                    f"""\
                [tool.hatch.build.hooks.protobuf]
                dependencies = ["hatch-protobuf @ {ROOT.as_uri()}"]
                """
                )
            )
        (project_dir / ".gitignore").write_text(GITIGNORE)
        create_module_dir(project_dir / "test_project")

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

        with open(project_dir / "pyproject.toml", "w") as fobj:
            fobj.write(PYPROJECT_HEADER)
            fobj.write(
                textwrap.dedent(
                    f"""\
                [tool.hatch.build.hooks.protobuf]
                dependencies = ["hatch-protobuf @ {ROOT.as_uri()}"]
                generate_grpc = false
                """
                )
            )
        (project_dir / ".gitignore").write_text(GITIGNORE)
        create_module_dir(project_dir / "test_project")

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

        with open(project_dir / "pyproject.toml", "w") as fobj:
            fobj.write(PYPROJECT_HEADER)
            fobj.write(
                textwrap.dedent(
                    f"""\
                [tool.hatch.build.hooks.protobuf]
                dependencies = ["hatch-protobuf @ {ROOT.as_uri()}"]
                generate_pyi = false
                """
                )
            )
        (project_dir / ".gitignore").write_text(GITIGNORE)
        create_module_dir(project_dir / "test_project")

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

        with open(project_dir / "pyproject.toml", "w") as fobj:
            fobj.write(PYPROJECT_HEADER)
            fobj.write(
                textwrap.dedent(
                    f"""\
                [tool.hatch.build.hooks.protobuf]
                dependencies = [
                    "hatch-protobuf @ {ROOT.as_uri()}",
                    "mypy-protobuf~=3.0",
                ]
                generate_pyi = false

                [[tool.hatch.build.hooks.protobuf.generators]]
                name = "mypy"
                outputs = ["{{proto_path}}/{{proto_name}}_pb2.pyi"]

                [[tool.hatch.build.hooks.protobuf.generators]]
                name = "mypy_grpc"
                outputs = ["{{proto_path}}/{{proto_name}}_pb2_grpc.pyi"]
                """
                )
            )
        (project_dir / ".gitignore").write_text(GITIGNORE)
        module_dir = project_dir / "test_project"
        create_module_dir(module_dir)

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

        with open(project_dir / "pyproject.toml", "w") as fobj:
            fobj.write(PYPROJECT_HEADER)
            fobj.write(
                textwrap.dedent(
                    f"""\
                [tool.hatch.build.hooks.protobuf]
                dependencies = [
                    "hatch-protobuf @ {ROOT.as_uri()}",
                    "mypy-protobuf~=3.0",
                ]
                generate_pyi = false

                [[tool.hatch.build.hooks.protobuf.generators]]
                name = "mypy"
                outputs = ["{{proto_path}}/{{proto_name}}_pb2.pyi"]

                [[tool.hatch.build.hooks.protobuf.generators]]
                name = "mypy_grpc"
                outputs = ["{{proto_path}}/{{proto_name}}_pb2_grpc.pyi"]
                """
                )
            )
        (project_dir / ".gitignore").write_text(GITIGNORE)
        module_dir = project_dir / "src" / "test_project"
        create_module_dir(module_dir)

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

        with open(project_dir / "pyproject.toml", "w") as fobj:
            fobj.write(PYPROJECT_HEADER)
            fobj.write(
                textwrap.dedent(
                    f"""\
                [tool.hatch.build.hooks.protobuf]
                dependencies = ["hatch-protobuf @ {ROOT.as_uri()}"]
                proto_paths = ["protos"]
                output_path = "src"
                """
                )
            )
        (project_dir / ".gitignore").write_text(GITIGNORE)

        module_dir = project_dir / "src" / "test_project"
        module_dir.mkdir(parents=True)
        (module_dir / "__init__.py").touch()

        # NB: the "test_project" subdir is necessary otherwise protoc generates
        # incorrect code
        proto_dir = project_dir / "protos" / "test_project"
        proto = importlib.resources.read_text("tests", "helloworld.proto")
        proto_dir.mkdir(parents=True)
        (proto_dir / "helloworld.proto").write_text(proto)

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
