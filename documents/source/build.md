# Building Makex

TODO: makex can build itself.

## python "build"

Download the source archive and use pip to build wheels/sdists.

```shell

makex_source="make-source-archive.zip"

mkdir makex

cd makex

# unzip the source archive
unzip ${makex_source} makex

pip install build

python -m build source
```

## Nuitka

There's a target in Makex file to build itself with nuitka.

```shell

makex run :nuitka

# get the path to the output
path=$(makex path :nuitka)

# copy the binary somewhere else
cp $path/makex ~/.local/bin 
```