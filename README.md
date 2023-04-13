# pipen-log2file

Save running logs to file for [pipen][1].

The log file is saved to `<workdir>/<pipeline>/.logs/run-<date-time>.log` by default.
A symlink `<workdir>/<pipeline>/run-latest.log` is created to the latest log file.

The xqute logs are also saved to `<workdir>/<pipeline>/<proc>/proc.xqute.log`

Note that the original handler of xqute logger is removed during pipeline running.

## Options

- `plugin_opts.log2file_xqute`: Whether to save xqute logs. Default: `True`.
    if False, the xqute logger will be kept intact.
- `plugin_opts.log2file_xqute_level`: The log level for xqute logger. Default: `INFO`.
- `plugin_opts.log2file_xqute_append`: Whether to append to the log file. Default: `False`.

## Installation

```
pip install -U pipen-log2file
```

## Enabling/Disabling the plugin

The plugin is registered via entrypoints. It's by default enabled. To disable it:
`plugins=[..., "no:log2file"]`, or uninstall this plugin.


[1]: https://github.com/pwwang/pipen
