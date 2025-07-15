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
| `import_site_packages` | `false` | Adds your Python `site-packages` directory to `--proto_path`, so you can [`import` `.proto` files from installed Python packages](#import-proto-files-from-site-packages). This *does not* add individual `.proto` files in `site-packages` as arguments to `protoc`. |
| `proto_paths` | `["."]` or `["src"]` | An array of paths to search for `.proto` files. Also passed as `--proto_path` arguments to `protoc`. This does not follow symlinks. |
| `output_path` | `"."` or `"src"` | The default output directory. This can be overridden on a per-generator basis for custom generators. |
| `library_paths` | `[]` | Similar to `proto_paths`, but **without** building the `_pb2.py` files, allowing imports from `.proto`s not included in the Python `site-packages` directory. |

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
plugin to the list of dependencies.

Options that can be set in generator sections:

| Key | Default | Description |
| --- | ------- | ----------- |
| `name` | required | The name of the plugin. The argument passed to protoc will be `--<name>_out`. |
| `outputs` | required | A list of paths (relative to `output_path`). See below for more information. |
| `output_path` | same as `output_path` from the main `protobuf` config section | Where to write generated files to. This is the value passed to the `--<name>_out` argument. |
| `protoc_plugin` | `None` | The protoc plugin to use for this generator, if any. Will be passed as --plugin to protoc. This is useful for plugins that are not installed in the Python environment. |
| `options` | `[]` | Extra parameters to be passed to the protoc plugin using [the `--<name>_opt` argument.][protobuf-pull-2284] |

Each entry in the `outputs` field is a template that depends on the `.proto` file being
processed. The string `{proto_name}` will be replaced with the base filename of each input .proto
file, and `{proto_path}` will be replaced with the path (relative to the proto_paths) of
the input proto files. For example, if `proto_paths` is set to `["src"]`, for the
input file `src/foo/bar/test.proto` "{proto_name}" will expand to "test" and
"{proto_path}" will expand to "foo/bar".

Here is an example using the TypeScript generator:

```
[[tool.hatch.build.hooks.protobuf.generators]]
name = "ts"
outputs = ["{proto_path}/{proto_name}.ts"]
output_path = "./frontend/src"
protoc_plugin = "./frontend/node_modules/.bin/protoc-gen-ts_proto"
```

[protobuf-pull-2284]: https://github.com/protocolbuffers/protobuf/pull/2284

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

### Import `.proto` files from `site-packages`

Setting `include_site_packages = true` causes the plugin to add your current
`site-packages` directory as a `--proto_path` when running `protoc`, *without*
trying to build a `_pb2.py` for *every* `.proto` file.

This allows your package to consume Protocol Buffer definitions from published
Python packages which include both `.proto` and `_pb2.py` files.

As an example, consider a gRPC service definition which includes a Protocol
Buffer message definiton from
[Google API common protos](https://github.com/googleapis/googleapis/tree/master/google/api):

```proto
// proto/example/v1/example.proto
syntax = "proto3";

package example.v1;

import "google/api/annotations.proto";

// The greeting service definition.
service Greeter {
  // Sends a greeting
  rpc SayHello(HelloRequest) returns (HelloReply) {
    option (google.api.http) = {
      get: "/say"
    };
  }
}

// The request message containing the user's name.
message HelloRequest {
  string name = 1;
}

// The response message containing the greetings
message HelloReply {
  string message = 1;
}
```

In this case, the
[`googleapis-common-protos` package](https://pypi.org/project/googleapis-common-protos/)
contains `annotations.proto` and a pre-built version of `annotations_pb2.py`,
which is normally installed in a directory tree layout which can be used by
*both* Python and `protoc`:

```
site-packages/google/api/
├── annotations_pb2.py
├── annotations.proto
├── auth_pb2.py
├── auth.proto
...
```

Setting `include_site_packages = true` makes your generated code contain imports
that reference the already-built bindings, and not rebuild them:

```python
# example/v1/example_pb2.py
from google.api import annotations_pb2 as google_dot_api_dot_annotations__pb2
```

If you had added the directory containing `google/api/annotations.proto` to this
plugin's `proto_paths` option, this would cause it to re-build Python files for
*all* `.proto` files in that directory, not just the things used for your
package, and stomp all over your `site-packages` directory.

> [!NOTE]
> You can only `import` Protocol Buffer definitions in `.proto` files from
> *non-editable* dependencies (ie: from ordinary packages published on PyPI or
> private registries).
>
> *Editable* dependencies (eg: installed with `pip install -e` or using
> [`uv` workspaces](https://docs.astral.sh/uv/concepts/projects/dependencies/#editable-dependencies))
> use a different directory layout which can't be imported from by `protoc`.

To consume Protocol Buffer definitions from published Python packages which
include only `_pb2.py` files, `library_paths` can be set to the directory
containing the `.proto` files.
For example, You can add [opentelemetry-proto](https://github.com/open-telemetry/opentelemetry-proto)
as a submodule in a project, and you will be able to import files from it after
including the following config:

```
[tool.hatch.build.hooks.protobuf]
library_paths = ["./libs/opentelemetry-proto"]
```
