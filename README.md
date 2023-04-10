# pipen-log2file

Save running logs to file for [pipen][1].

The log file is saved to `<workdir>/<pipeline>/.logs/run-<date-time>.log` by default.
A symlink `<workdir>/<pipeline>/run-latest.log` is created to the latest log file.

## Installation

```
pip install -U pipen-log2file
```

## Enabling/Disabling the plugin

The plugin is registered via entrypoints. It's by default enabled. To disable it:
`plugins=[..., "no:log2file"]`, or uninstall this plugin.


[1]: https://github.com/pwwang/pipen
