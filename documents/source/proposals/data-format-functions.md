# Data Format Functions

## Rationale

Builds often use json, toml, yaml files to define configuration.

The purpose of this feature is to provide functions to encode data from Makex files into JSON, 
which may be passed as arguments, or which may be written to files.

## Syntax

```python

DATA = {
    
}

data: EncodedData = json_encode(DATA)
data: EncodedData = toml_encode(DATA)
data: EncodedData = yaml_encode(DATA)

...

task(
    name="",
    steps=[
        - write(path, data)
    ]
)
```

## Formats

- JSON: json
- YAML: yaml
- TOML: toml
- Lines: output a list of strings line by line
- CSV: csv?

## Rejected Ideas

### Decoding

Decoding data while reading makex files will slow down parsing/evaluation. Might be a better idea to only include encode.

```python
decode(format="json", file="", extract="name.*")
decode(format="json", data="", extract="name.*")

json.decode(string|path).extract("$.name.*") -> DecodedData
```

Decoding would require some kind DecodedData object whose values are evaluated lazily.

### Alternate syntaxes


- `encode(format="lines", data=[])`
- `encode(data={"name": {"*": COMPONENTS}}, indent=2)`

### Separate serialize action

Simply a write() action with contents of an encoding() function (`write(file, encode_json({}, indent=2))`):

- `serialize(file, format="json", data={}, indent=2)`
- `serialize(file, data={}, json=data, indent=2)`
- `serialize(file, format="lines", data=[], yaml=data, indent=2)`

