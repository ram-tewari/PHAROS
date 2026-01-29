/**
 * Infrastructure Section
 * 
 * Phase 7: Ops & Edge Management (Option C)
 * Database, event bus, cache, workers, and ML model monitoring
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Database, Activity, HardDrive, Cpu, Brain } from 'lucide-react';
import { MetricCard } from './MetricCard';
import { StatusBadge } from './StatusBadge';
import type {
  DatabaseMetrics,
  EventBusMetrics,
  EventHistoryItem,
  CacheStats,
  WorkerStatus,
  ModelHealthMetrics,
} from '@/types/monitoring';

interface InfrastructureSectionProps {
  database?: DatabaseMetrics;
  eventBus?: EventBusMetrics;
  eventHistory?: EventHistoryItem[];
  cache?: CacheStats;
  workers?: WorkerStatus;
  modelHealth?: ModelHealthMetrics;
}

export function InfrastructureSection({
  database,
  eventBus,
  eventHistory,
  cache,
  workers,
  modelHealth,
}: InfrastructureSectionProps) {
  return (
    <div className="space-y-6">
      {/* Database Monitor */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            Database
          </CardTitle>
        </CardHeader>
        <CardContent>
          {database ? (
            <div className="grid gap-4 md:grid-cols-3">
              <MetricCard
                title="Connection Pool"
                value={`${database.connection_pool.active}/${database.connection_pool.max}`}
                status={database.connection_pool.utilization > 80 ? 'warning' : 'success'}
              />
              <MetricCard
                title="Avg Query Time"
                value={database.query_performance.avg_query_time_ms}
                unit="ms"
                status={database.query_performance.avg_query_time_ms > 100 ? 'warning' : 'success'}
              />
              <MetricCard
                title="Slow Queries"
                value={database.query_performance.slow_queries}
                status={database.query_performance.slow_queries > 10 ? 'warning' : 'success'}
              />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Loading database metrics...</p>
          )}
        </CardContent>
      </Card>

      {/* Event Bus Monitor */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Event Bus
          </CardTitle>
        </CardHeader>
        <CardContent>
          {eventBus ? (
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-4">
                <MetricCard
                  title="Events Emitted"
                  value={eventBus.events_emitted}
                />
                <MetricCard
                  title="Events Received"
                  value={eventBus.events_received}
                />
                <MetricCard
                  title="Latency (P95)"
                  value={eventBus.event_latency_ms.p95}
                  unit="ms"
                  status={eventBus.event_latency_ms.p95 > 1 ? 'warning' : 'success'}
                />
                <MetricCard
                  title="Failed Deliveries"
                  value={eventBus.failed_deliveries}
                  status={eventBus.failed_deliveries > 0 ? 'error' : 'success'}
                />
              </div>
              
              {eventHistory && eventHistory.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium mb-2">Recent Events</h4>
                  <div className="space-y-1 max-h-40 overflow-y-auto">
                    {eventHistory.slice(0, 10).map((event, i) => (
                      <div key={i} className="text-xs flex items-center justify-between py-1 border-b">
                        <span className="font-mono">{event.type}</span>
                        <span className="text-muted-foreground">
                          {new Date(event.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Loading event bus metrics...</p>
          )}
        </CardContent>
      </Card>

      {/* Cache Monitor */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HardDrive className="h-5 w-5" />
            Cache
          </CardTitle>
        </CardHeader>
        <CardContent>
          {cache ? (
            <div className="grid gap-4 md:grid-cols-3">
              <MetricCard
                title="Hit Rate"
                value={`${cache.hit_rate.toFixed(1)}%`}
                status={cache.hit_rate < 50 ? 'warning' : 'success'}
              />
              <MetricCard
                title="Cache Size"
                value={cache.size_mb.toFixed(2)}
                unit="MB"
              />
              <MetricCard
                title="Eviction Rate"
                value={cache.eviction_rate.toFixed(2)}
                status={cache.eviction_rate > 10 ? 'warning' : 'success'}
              />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Loading cache stats...</p>
          )}
        </CardContent>
      </Card>

      {/* Workers Monitor */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-5 w-5" />
            Workers
          </CardTitle>
        </CardHeader>
        <CardContent>
          {workers ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">Active Workers</p>
                  <p className="text-2xl font-bold">{workers.active_workers}</p>
                </div>
                <StatusBadge status={workers.worker_health} />
              </div>
              
              <div className="grid gap-4 md:grid-cols-3">
                <MetricCard
                  title="Queue Length"
                  value={workers.queue_length}
                  status={workers.queue_length > 100 ? 'warning' : 'success'}
                />
                <MetricCard
                  title="Processing Rate"
                  value={workers.processing_rate?.toFixed(2) ?? '0.00'}
                  unit="tasks/s"
                />
                <MetricCard
                  title="Failed Tasks"
                  value={workers.failed_tasks ?? 0}
                  status={(workers.failed_tasks ?? 0) > 0 ? 'error' : 'success'}
                />
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Loading worker status...</p>
          )}
        </CardContent>
      </Card>

      {/* ML Models Monitor */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5" />
            ML Models
          </CardTitle>
        </CardHeader>
        <CardContent>
          {modelHealth?.models ? (
            <div className="grid gap-4 md:grid-cols-3">
              {Object.entries(modelHealth.models).map(([name, model]) => (
                <Card key={name}>
                  <CardContent className="p-4">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <p className="font-medium capitalize">{name}</p>
                        <span className={`text-xs ${model.loaded ? 'text-green-500' : 'text-red-500'}`}>
                          {model.loaded ? '✓ Loaded' : '✗ Not Loaded'}
                        </span>
                      </div>
                      <div className="text-xs space-y-1">
                        <p className="text-muted-foreground">
                          Inference: {model.inference_time_ms}ms
                        </p>
                        <p className="text-muted-foreground">
                          Memory: {model.memory_mb.toFixed(1)}MB
                        </p>
                        {model.error_rate > 0 && (
                          <p className="text-red-500">
                            Error rate: {(model.error_rate * 100).toFixed(1)}%
                          </p>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Loading model health...</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
