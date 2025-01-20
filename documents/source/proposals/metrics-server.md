---
status: "Draft"
---
# Metrics Server

Consider exposing metrics over a client/server/http connection.

## Metrics Format

We may use a prometheus/opentsdb metrics format:

```
{metric_name}{{labels}} {value} {timestamp} 
```

Where `{labels}` may be names and values separated by commas e.g. `{label_name}={label_value}`

### Metric names 

Metric names may contain ASCII letters, digits, underscores, and colons. 
It must match the regex [a-zA-Z_:][a-zA-Z0-9_:]*.

### Histograms

```
{metric_name}_bucket{{le={maximum_value}}} {value} 
{metric_name}_bucket{{le="+Inf"}} {count}  
{metric_name}_count {count}
{metric_name}_sum {sum}
```

Metric name: The base name of the histogram metric.
The `bucket` suffix is appended to the metric name to indicate a bucket.
The `le` label stands for "less than or equal to" and defines the upper bound of the bucket.

Each bucket is stored in a separate metric suffixed with _bucket and the maximum value for that time series is in the label le.
There is always a largest bucket with infinite maximum value {le="Inf"} which will always have the same value as _count. 

## Metrics

- `makex{version="", ...}`: Metrics/metadata about the metrics.
- `makex_actions_executed_total{type="execute|write|..."}`: Number of actions executed by type.
- `makex_executable_executions{path="/usr/bin/..."}`: Total number of executions by 
- `makex_memory_usage`: Current memory usage in bytes
- `makex_tasks_executed_total`: Total number of tasks run.
- `makex_tasks_executing`: Tasks currently executing.
- `makex_tasks_waiting`: Tasks currently waiting.
- `makex_total_memory`: Total memory available.

See https://prometheus.io/docs/practices/naming/ for best practices.

## Related Tools

### Graphical

Use a tool like [Metricat](https://metricat.dev/) locally to view these metrics in real time.

### Command Line

- https://github.com/nalbury/promql-cli
- https://github.com/sklarsa/operator-prom-metrics-viewer
- https://github.com/slok/grafterm
