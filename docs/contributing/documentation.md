# Documentation

All documentation is referenced in and deployed to our docs mono repo via git submodules:

[https://github.com/poly-hammer/poly-hammer-docs](https://github.com/poly-hammer/poly-hammer-docs)

The finally docs build can be seen here:

[https://docs.polyhammer.com](https://docs.polyhammer.com)

## Testing Locally

The documentation sites are static html sites that are generated using [mkdocs](https://www.mkdocs.org/). To get the docs working locally run these commands:

``` shell
pip install -r requirements.txt
mkdocs serve
```

The site should now be available to preview at:

[http://localhost:8080](http://localhost:8000)
