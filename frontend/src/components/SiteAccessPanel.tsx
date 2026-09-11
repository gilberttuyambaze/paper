import { useEffect, useState } from 'react';
import { AlertTriangle, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { fetchAdminUsers, fetchHeartbeatStatus, fetchSiteAccessSettings, heartbeatStreamUrl, runHeartbeatNow, saveSiteAccessSettings, transferSuperAdmin, type HeartbeatStatus, type SiteAccessSettings, type UserProfile } from '@/lib/client';
import { toast } from '@/lib/messages';
import { useAuth } from '@/contexts/AuthContext';
import { getStoredAuthToken } from '@/lib/auth';

const roles = ['super_admin', 'admin', 'cp', 'lecturer', 'content_manager', 'verified_contributor', 'normal'];

export default function SiteAccessPanel() {
  const [settings, setSettings] = useState<SiteAccessSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [replacement, setReplacement] = useState('');
  const [heartbeat, setHeartbeat] = useState<HeartbeatStatus | null>(null);
  const [runningHeartbeat, setRunningHeartbeat] = useState(false);
  const [heartbeatActivity, setHeartbeatActivity] = useState<Array<{ message: string; state: string; timestamp: string }>>([]);
  const [heartbeatStreamConnected, setHeartbeatStreamConnected] = useState(false);
  const { user } = useAuth();
  useEffect(() => { void fetchSiteAccessSettings().then(setSettings).catch(() => toast.error('Unable to load site access settings')); }, []);
  useEffect(() => { void fetchAdminUsers({ limit: 100 }).then((data) => setUsers(data.items)).catch(() => undefined); }, []);
  useEffect(() => {
    let active = true;
    const refreshHeartbeat = () => { void fetchHeartbeatStatus().then((next) => { if (active) setHeartbeat(next); }).catch(() => undefined); };
    refreshHeartbeat();
    const interval = window.setInterval(refreshHeartbeat, 3000);
    return () => { active = false; window.clearInterval(interval); };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const connect = async () => {
      const token = getStoredAuthToken();
      if (!token) return;
      while (!controller.signal.aborted) try {
        const response = await fetch(heartbeatStreamUrl(), { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal });
        if (!response.ok || !response.body) throw new Error(`Heartbeat stream returned ${response.status}`);
        setHeartbeatStreamConnected(true);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (!controller.signal.aborted) {
          const chunk = await reader.read();
          if (chunk.done) break;
          buffer += decoder.decode(chunk.value, { stream: true });
          const events = buffer.split('\n\n');
          buffer = events.pop() || '';
          events.forEach((event) => {
            const data = event.split('\n').find((line) => line.startsWith('data: '))?.slice(6);
            if (!data) return;
            try { const activity = JSON.parse(data) as { message: string; state: string; timestamp: string }; setHeartbeatActivity((current) => [activity, ...current].slice(0, 8)); } catch { /* Ignore an incomplete stream event. */ }
          });
        }
        setHeartbeatStreamConnected(false);
        if (!controller.signal.aborted) await new Promise((resolve) => window.setTimeout(resolve, 2000));
      } catch (error) {
        if (!controller.signal.aborted) { setHeartbeatStreamConnected(false); console.debug('Heartbeat activity stream disconnected', error); await new Promise((resolve) => window.setTimeout(resolve, 2000)); }
      }
    };
    void connect();
    return () => controller.abort();
  }, []);
  if (!settings) return null;
  const update = (next: Partial<SiteAccessSettings>) => setSettings((current) => current ? { ...current, ...next } : current);
  const save = async () => {
    try { setSaving(true); setSettings(await saveSiteAccessSettings(settings)); toast.success('Site access settings saved'); }
    catch { toast.error('Only the Super Admin can change these settings'); }
    finally { setSaving(false); }
  };
  const changeSuperAdmin = async () => {
    const selected = users.find((item) => String(item.id) === replacement);
    if (!selected || !window.confirm(`Transfer Super Admin to ${selected.display_name}?`)) return;
    try { await transferSuperAdmin(selected.id); toast.success('Super Admin transferred. Refreshing your session.'); window.location.reload(); }
    catch { toast.error('Super Admin transfer failed'); }
  };
  const runNow = async () => { try { setRunningHeartbeat(true); const result = await runHeartbeatNow(); setHeartbeat(result.heartbeat); toast.success(result.success ? 'Heartbeat completed' : `Heartbeat not run: ${result.reason}`); } catch { toast.error('Heartbeat could not be run'); } finally { setRunningHeartbeat(false); } };
  return <Card className="theme-panel border-primary/20">
    <CardHeader><CardTitle className="flex items-center gap-2"><Save className="h-5 w-5" />Site Access &amp; Security</CardTitle></CardHeader>
    <CardContent className="space-y-6">
      <div className="space-y-3"><Label>Super Admin</Label><p className="text-sm text-muted-foreground">Current account: {user?.name || user?.email || 'Current account'} (only one account is allowed).</p><div className="flex flex-col gap-2 sm:flex-row"><select className="h-10 flex-1 rounded-md border bg-background px-3" value={replacement} onChange={(event) => setReplacement(event.target.value)}><option value="">Change Super Admin...</option>{users.filter((item) => item.role !== 'super_admin').map((item) => <option key={item.id} value={item.id}>{item.display_name} ({item.email || item.user_id})</option>)}</select><Button variant="outline" disabled={!replacement} onClick={() => void changeSuperAdmin()}>Change Super Admin</Button></div></div>
      {settings.maintenance_mode && <div className="flex items-center gap-2 rounded-lg border border-warning/40 bg-warning-soft p-3 text-sm"><AlertTriangle className="h-4 w-4" />Maintenance Mode is active. Public access is currently blocked.</div>}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2"><Label>Maintenance Mode</Label><select className="h-10 w-full rounded-md border bg-background px-3" value={settings.maintenance_mode ? 'on' : 'off'} onChange={(event) => update({ maintenance_mode: event.target.value === 'on' })}><option value="off">Off</option><option value="on">On</option></select></div>
        <div className="space-y-2"><Label>Who can upload?</Label><select className="h-10 w-full rounded-md border bg-background px-3" value={settings.upload_access_mode} onChange={(event) => update({ upload_access_mode: event.target.value as SiteAccessSettings['upload_access_mode'] })}><option value="nobody">Nobody</option><option value="authenticated">Any authenticated user</option><option value="selected_roles">Selected roles</option></select></div>
      </div>
      <div className="space-y-2"><Label>Maintenance message</Label><Input value={settings.maintenance_message} onChange={(event) => update({ maintenance_message: event.target.value })} /></div>
      <div className="space-y-2"><Label>Allowed resource types</Label><div className="flex gap-6">{[['book', 'Books'], ['paper', 'Papers']].map(([value, label]) => <label key={value} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.allowed_resource_types.includes(value)} onChange={(event) => update({ allowed_resource_types: event.target.checked ? [...settings.allowed_resource_types, value] : settings.allowed_resource_types.filter((item) => item !== value) })} />{label}</label>)}</div></div>
      <div className="space-y-2"><Label>Allowed roles</Label><div className="grid gap-2 sm:grid-cols-2">{roles.map((role) => <label key={role} className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={settings.upload_access_mode !== 'selected_roles'} checked={settings.upload_roles.includes(role)} onChange={(event) => update({ upload_roles: event.target.checked ? [...settings.upload_roles, role] : settings.upload_roles.filter((item) => item !== role) })} />{role.replace('_', ' ')}</label>)}</div></div>
      <div className="space-y-4 border-t pt-5"><div className="grid gap-3 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.8fr)] xl:items-start">
        <div className="min-w-0">
         </div>{heartbeat && <div className="theme-soft-panel w-full rounded-lg border border-primary/10 p-3 text-sm"><div className="flex items-start justify-between gap-3"><div className="min-w-0 space-y-1"><div className="flex items-center gap-2 font-medium text-foreground"><span>Live heartbeat status</span><span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-primary"><span className={`h-2 w-2 rounded-full ${heartbeatStreamConnected ? 'animate-pulse bg-success' : 'bg-muted-foreground'}`} />{heartbeatStreamConnected ? 'Live stream connected' : 'Reconnecting stream'}</span></div><p className="text-muted-foreground">{heartbeat.activity_message}</p></div><Button variant="outline" size="sm" disabled={runningHeartbeat || !settings.heartbeat_enabled} onClick={() => void runNow()}>{runningHeartbeat ? 'Running…' : 'Run heartbeat now'}</Button></div><div className="mt-3 grid gap-2 text-xs sm:grid-cols-2"><div className="flex items-center justify-between gap-2"><span>Status</span><span className="font-medium text-foreground">{heartbeat.status}</span></div><div className="flex items-center justify-between gap-2"><span>Attempts / success</span><span className="font-medium text-foreground">{heartbeat.total_attempts} / {heartbeat.total_successes}</span></div><div className="flex items-center justify-between gap-2"><span>Scheduler</span><span className="font-medium text-foreground">{heartbeat.scheduler_running ? 'running' : 'standby'}</span></div><div className="flex items-center justify-between gap-2"><span>Next check</span><span className="font-medium text-foreground">{heartbeat.next_scheduled_at ? new Date(heartbeat.next_scheduled_at).toLocaleString() : 'Preparing...'}</span></div></div><div className="mt-3 rounded-md border border-border/60 bg-background/40 p-2"><div className="grid gap-2 text-xs sm:grid-cols-2"><div className="flex items-center justify-between gap-3"><span>Status</span><span className="font-medium text-foreground">{heartbeat.status}</span></div><div className="flex items-center justify-between gap-3"><span>Scheduler</span><span className="font-medium text-foreground">{heartbeat.scheduler_running ? 'running' : 'not running'}</span></div><div className="flex items-center justify-between gap-3"><span>Attempts</span><span className="font-medium text-foreground">{heartbeat.total_attempts}</span></div><div className="flex items-center justify-between gap-3"><span>Successes</span><span className="font-medium text-foreground">{heartbeat.total_successes}</span></div><div className="flex items-center justify-between gap-3"><span>Failures</span><span className="font-medium text-foreground">{heartbeat.total_failures}</span></div><div className="flex items-center justify-between gap-3"><span>Consecutive failures</span><span className="font-medium text-foreground">{heartbeat.consecutive_failures}</span></div><div className="flex items-center justify-between gap-3"><span>Retries</span><span className="font-medium text-foreground">{heartbeat.retry_attempts}</span></div><div className="flex items-center justify-between gap-3"><span>Last attempt</span><span className="font-medium text-foreground">{heartbeat.last_attempt_at || 'Never'}</span></div><div className="flex items-center justify-between gap-3"><span>Last success</span><span className="font-medium text-foreground">{heartbeat.last_success_at || 'Never'}</span></div><div className="flex items-center justify-between gap-3"><span>Last failure</span><span className="font-medium text-foreground">{heartbeat.last_failure_at || 'Never'}</span></div><div className="flex items-center justify-between gap-3"><span>Next check</span><span className="font-medium text-foreground">{heartbeat.next_scheduled_at || 'Not scheduled'}</span></div><div className="flex items-center justify-between gap-3"><span>Next retry</span><span className="font-medium text-foreground">{heartbeat.next_retry_at || 'None'}</span></div></div></div>{heartbeatActivity.length > 0 && <div className="mt-3 border-t pt-2"><p className="mb-2 font-medium text-foreground">Live activity console</p><div className="max-h-44 space-y-1.5 overflow-y-auto rounded-md bg-foreground/[0.04] p-2 font-mono">{heartbeatActivity.map((activity) => <p className="text-xs text-muted-foreground" key={`${activity.timestamp}-${activity.message}`}><span className="mr-1 text-primary">[{new Date(activity.timestamp).toLocaleTimeString()}]</span>{activity.message}</p>)}</div></div>}</div>}</div><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.heartbeat_enabled} onChange={(event) => update({ heartbeat_enabled: event.target.checked })} />Enable heartbeat</label><div className="grid gap-3 sm:grid-cols-2"><label className="text-sm">Minimum checks per week<input className="mt-1 h-10 w-full rounded-md border bg-background px-3" type="number" min="1" max="7" value={settings.heartbeat_min_weekly_checks} onChange={(event) => update({ heartbeat_min_weekly_checks: Number(event.target.value) })} /></label><label className="text-sm">Maximum checks per week<input className="mt-1 h-10 w-full rounded-md border bg-background px-3" type="number" min="1" max="7" value={settings.heartbeat_max_weekly_checks} onChange={(event) => update({ heartbeat_max_weekly_checks: Number(event.target.value) })} /></label><label className="text-sm">Retry delay (hours)<input className="mt-1 h-10 w-full rounded-md border bg-background px-3" type="number" min="1" max="72" value={settings.heartbeat_retry_delay_hours} onChange={(event) => update({ heartbeat_retry_delay_hours: Number(event.target.value) })} /></label><label className="text-sm">Retry jitter (minutes)<input className="mt-1 h-10 w-full rounded-md border bg-background px-3" type="number" min="0" max="720" value={settings.heartbeat_retry_jitter_minutes} onChange={(event) => update({ heartbeat_retry_jitter_minutes: Number(event.target.value) })} /></label><label className="text-sm">Maximum retry attempts<input className="mt-1 h-10 w-full rounded-md border bg-background px-3" type="number" min="0" max="5" value={settings.heartbeat_max_retry_attempts} onChange={(event) => update({ heartbeat_max_retry_attempts: Number(event.target.value) })} /></label></div><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.heartbeat_retry_enabled} onChange={(event) => update({ heartbeat_retry_enabled: event.target.checked })} />Enable bounded retries</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.heartbeat_run_on_startup} onChange={(event) => update({ heartbeat_run_on_startup: event.target.checked })} />Run once after startup</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.heartbeat_notify_admin ?? true} onChange={(event) => update({ heartbeat_notify_admin: event.target.checked })} />Send email notification to admin on heartbeat runs</label>{heartbeat && <div className="space-y-2 text-sm text-muted-foreground"><div className="grid gap-2 sm:grid-cols-2"><span>Status: {heartbeat.status}</span><span>Scheduler: {heartbeat.scheduler_running ? 'running' : 'not running'}</span><span>Attempts: {heartbeat.total_attempts}</span><span>Successes: {heartbeat.total_successes}</span><span>Failures: {heartbeat.total_failures}</span><span></span><span>Retries: {heartbeat.retry_attempts}</span><span>Last attempt: {heartbeat.last_attempt_at || 'Never'}</span><span>Last success: {heartbeat.last_success_at || 'Never'}</span><span>Last failure: {heartbeat.last_failure_at || 'Never'}</span><span>Next check: {heartbeat.next_scheduled_at || 'Not scheduled'}</span><span>Next retry: {heartbeat.next_retry_at || 'None'}</span></div>{['degraded', 'failed'].includes(heartbeat.status) && <p className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-destructive">⚠ Heartbeat degraded. Consecutive failures: {heartbeat.consecutive_failures}. Last successful heartbeat: {heartbeat.last_success_at || 'Never'}.</p>}</div>}</div>
      <Button onClick={() => void save()} disabled={saving}><Save className="mr-2 h-4 w-4" />{saving ? 'Saving...' : 'Save Settings'}</Button>
    </CardContent>
  </Card>;
}
