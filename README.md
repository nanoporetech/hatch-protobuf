# Hatch Protocol Buffers Generator

This Hatch plugin uses grpcio to generate Python files from Protocol Buffers `.proto` files.


## Usage

You will need to add `hatch-protobuf` to your project's `pyproject.toml`:

```
[tool.hatch.build.hooks.protobuf]
dependencies = ["hatch-protobuf"]
```

There are a few options that can be set in the `[tool.hatch.build.hooks.protobuf]`
section:

| Key | Default | Description |
| --- | ------- | ----------- |
| `generate_grpc` | `true` | Whether to generate gRPC output files. |
| `generate_pyi` | `true` | Whether to generate .pyi output files. Note that these are not generated for the gRPC output. You may want to use mypy-protobuf instead. |
| `proto_paths` | `["."]` or `["src"]` | An array of paths to search for `.proto` files. Also passed as `--proto_path` arguments to `protoc`. |
| `output_path` | `"."` or `"src"` | The default output directory. This can be overridden on a per-generator basis for custom generators. |

Hatch-protobuf will guess whether to use "src" as the default input/output directory in
a similar way to the [wheel builder][wheel-builder-defaults]. If
`src/<NAME>/__init__.py` exists, but `<NAME>/__init__.py` does not, it will use "src" as
the default for `proto_paths` and `output_path`. Otherwise it will use "." as the
default for both.

[wheel-builder-defaults]: https://hatch.pypa.io/latest/plugins/builder/wheel/#default-file-selection

### Custom generators

If you want to use custom generators (not just the python, gRPC and pyi ones built in to
the version of protoc that ships with grpcio-tools), you can add them in
`[[tool.hatch.build.hooks.protobuf.generators]]` sections. You will also need to add the
plugin to the list of dependencies. See the "Mypy output" section below for an example.
Options that can be set in generator sections:

| Key | Default | Description |
| --- | ------- | ----------- |
| `name` | required | The name of the plugin. The argument passed to protoc will be `--<name>_out`. |
| `outputs` | required | A list of paths (relative to `output_path`). See below for more information. |
| `output_path` | same as `output_path` from the main `protobuf` config section | Where to write generated files to. This is the value passed to the `--<name>_out` argument. |

Each entry in the `outputs` field is a template that depends on the `.proto` file being
processed. The string `{proto_name}` will be replaced with the base filename of each input .proto
file, and `{proto_path}` will be replaced with the path (relative to the proto_paths) of
the input proto files. For example, if `proto_paths` is set to `["src"]`, for the
input file `src/foo/bar/test.proto` "{proto_name}" will expand to "test" and
"{proto_path}" will expand to "foo/bar".

### Mypy output

The [mypy-protobuf](https://pypi.org/project/mypy-protobuf/) package provides mypy stub
files with comments copied from the input `.proto` files. Here is an example of how to
use it in your `pyproject.toml`:

```
[tool.hatch.build.hooks.protobuf]
dependencies = [
    "hatch-protobuf",
    "mypy-protobuf~=3.0",
]
generate_pyi = false  # we'll let mypy-protobuf do this

[[tool.hatch.build.hooks.protobuf.generators]]
name = "mypy"
outputs = ["{proto_path}/{proto_name}_pb2.pyi"]

[[tool.hatch.build.hooks.protobuf.generators]]
name = "mypy_grpc"
outputs = ["{proto_path}/{proto_name}_pb2_grpc.pyi"]
```
