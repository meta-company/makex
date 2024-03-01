(actions)=
# Creating Actions

TODO: This needs to be fleshed out more with argument processing.
TODO: Most things are an extension of shell/execute, and/or may use copy/sync/etc.

```{note}

Coming soon.
```

```python

from makex.api.v1 import Action, run, Help

class CustomScript(Action):
    """
    Define a runnable named custom()
    """
    name = "custom"
    
    def help(self, types) -> Help:
        return 
    
    def help_cli(self):
        # return help text for the command approriate for 
        pass
    
    def help_html(self):
        # return html help
        pass
    
    def help_url(self):
        # return a URL we can open to learn more about the command
        pass
    
    def run(self, ctx, target):
        # you can do anything here that you can do in python
        # use the run() function to run stuff while handling stdout properly
        # target.path is a Path object represnting the output path
        # target.input_path is a Path object representing the input path
        
        # a dictionary of all arguments passed to the function
        # the values are resolved as necessary *before* this is run
        # e.g. Finds/Globs and other iterables are expanded.
        self.arguments["name"]
        
        pass
```

