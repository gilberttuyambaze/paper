import { useEffect, useState } from 'react';
import { AlertTriangle, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { fetchAdminUsers, fetchHeartbeatStatus, fetchSiteAccessSettings, runHeartbeatNow, saveSiteAccessSettings, transferSuperAdmin, type HeartbeatStatus, type SiteAccessSettings, type UserProfile } from '@/lib/client';
import { toast } from '@/lib/messages';
import { useAuth } from '@/contexts/AuthContext';

const roles = ['super_admin', 'admin', 'cp', 'lecturer', 'content_manager', 'verified_contributor', 'normal'];

export default function SiteAccessPanel() {
  const [settings, setSettings] = useState<SiteAccessSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [replacement, setReplacement] = useState('');
  const [heartbeat, setHeartbeat] = useState<HeartbeatStatus | null>(null);
  const [runningHeartbeat, setRunningHeartbeat] = useState(false);
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
      {heartbeat && <div className="theme-soft-panel space-y-2 rounded-lg p-3 text-sm"><div className="flex items-center justify-between"><span className="font-medium text-foreground">Live heartbeat status</span><span className="text-xs uppercase tracking-wide text-primary">{heartbeat.scheduler_running ? 'Scheduler online' : 'Monitoring'}</span></div><p className="text-muted-foreground">{heartbeat.activity_message}</p><div className="flex justify-between"><span>Status</span><span className="font-medium text-foreground">{heartbeat.status}</span></div><div className="flex justify-between"><span>Attempts / successes</span><span className="font-medium text-foreground">{heartbeat.total_attempts} / {heartbeat.total_successes}</span></div><div className="flex justify-between"><span>Next scheduled check</span><span className="font-medium text-foreground">{heartbeat.next_scheduled_at ? new Date(heartbeat.next_scheduled_at).toLocaleString() : 'Preparing...'}</span></div></div>}
      <div className="space-y-3"><Label>Super Admin</Label><p className="text-sm text-muted-foreground">Current account: {user?.name || user?.email || 'Current account'} (only one account is allowed).</p><div className="flex flex-col gap-2 sm:flex-row"><select className="h-10 flex-1 rounded-md border bg-background px-3" value={replacement} onChange={(event) => setReplacement(event.target.value)}><option value="">Change Super Admin...</option>{users.filter((item) => item.role !== 'super_admin').map((item) => <option key={item.id} value={item.id}>{item.display_name} ({item.email || item.user_id})</option>)}</select><Button variant="outline" disabled={!replacement} onClick={() => void changeSuperAdmin()}>Change Super Admin</Button></div></div>
      {settings.maintenance_mode && <div className="flex items-center gap-2 rounded-lg border border-warning/40 bg-warning-soft p-3 text-sm"><AlertTriangle className="h-4 w-4" />Maintenance Mode is active. Public access is currently blocked.</div>}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2"><Label>Maintenance Mode</Label><select className="h-10 w-full rounded-md border bg-background px-3" value={settings.maintenance_mode ? 'on' : 'off'} onChange={(event) => update({ maintenance_mode: event.target.value === 'on' })}><option value="off">Off</option><option value="on">On</option></select></div>
        <div className="space-y-2"><Label>Who can upload?</Label><select className="h-10 w-full rounded-md border bg-background px-3" value={settings.upload_access_mode} onChange={(event) => update({ upload_access_mode: event.target.value as SiteAccessSettings['upload_access_mode'] })}><option value="nobody">Nobody</option><option value="authenticated">Any authenticated user</option><option value="selected_roles">Selected roles</option></select></div>
      </div>
      <div className="space-y-2"><Label>Maintenance message</Label><Input value={settings.maintenance_message} onChange={(event) => update({ maintenance_message: event.target.value })} /></div>
      <div className="space-y-2"><Label>Allowed resource types</Label><div className="flex gap-6">{[['book', 'Books'], ['paper', 'Papers']].map(([value, label]) => <label key={value} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.allowed_resource_types.includes(value)} onChange={(event) => update({ allowed_resource_types: event.target.checked ? [...settings.allowed_resource_types, value] : settings.allowed_resource_types.filter((item) => item !== value) })} />{label}</label>)}</div></div>
      <div className="space-y-2"><Label>Allowed roles</Label><div className="grid gap-2 sm:grid-cols-2">{roles.map((role) => <label key={role} className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={settings.upload_access_mode !== 'selected_roles'} checked={settings.upload_roles.includes(role)} onChange={(event) => update({ upload_roles: event.target.checked ? [...settings.upload_roles, role] : settings.upload_roles.filter((item) => item !== role) })} />{role.replace('_', ' ')}</label>)}</div></div>
      <div className="space-y-4 border-t pt-5"><div><Label>Database Health / Activity</Label><p className="mt-1 text-sm text-muted-foreground">Only the dedicated system-health record is updated. Supabase applies its own inactivity rules.</p></div><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.heartbeat_enabled} onChange={(event) => update({ heartbeat_enabled: event.target.checked })} />Enable heartbeat</label><div className="grid gap-3 sm:grid-cols-2"><label className="text-sm">Minimum checks per week<input className="mt-1 h-10 w-full rounded-md border bg-background px-3" type="number" min="1" max="7" value={settings.heartbeat_min_weekly_checks} onChange={(event) => update({ heartbeat_min_weekly_checks: Number(event.target.value) })} /></label><label className="text-sm">Maximum checks per week<input className="mt-1 h-10 w-full rounded-md border bg-background px-3" type="number" min="1" max="7" value={settings.heartbeat_max_weekly_checks} onChange={(event) => update({ heartbeat_max_weekly_checks: Number(event.target.value) })} /></label><label className="text-sm">Retry delay (hours)<input className="mt-1 h-10 w-full rounded-md border bg-background px-3" type="number" min="1" max="72" value={settings.heartbeat_retry_delay_hours} onChange={(event) => update({ heartbeat_retry_delay_hours: Number(event.target.value) })} /></label><label className="text-sm">Retry jitter (minutes)<input className="mt-1 h-10 w-full rounded-md border bg-background px-3" type="number" min="0" max="720" value={settings.heartbeat_retry_jitter_minutes} onChange={(event) => update({ heartbeat_retry_jitter_minutes: Number(event.target.value) })} /></label><label className="text-sm">Maximum retry attempts<input className="mt-1 h-10 w-full rounded-md border bg-background px-3" type="number" min="0" max="5" value={settings.heartbeat_max_retry_attempts} onChange={(event) => update({ heartbeat_max_retry_attempts: Number(event.target.value) })} /></label></div><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.heartbeat_retry_enabled} onChange={(event) => update({ heartbeat_retry_enabled: event.target.checked })} />Enable bounded retries</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.heartbeat_run_on_startup} onChange={(event) => update({ heartbeat_run_on_startup: event.target.checked })} />Run once after startup</label>{heartbeat && <div className="space-y-2 text-sm text-muted-foreground"><div className="grid gap-2 sm:grid-cols-2"><span>Status: {heartbeat.status}</span><span>Scheduler: {heartbeat.scheduler_running ? 'running' : 'not running'}</span><span>Attempts: {heartbeat.total_attempts}</span><span>Successes: {heartbeat.total_successes}</span><span>Failures: {heartbeat.total_failures}</span><span>Consecutive failures: {heartbeat.consecutive_failures}</span><span>Retries: {heartbeat.retry_attempts}</span><span>Last attempt: {heartbeat.last_attempt_at || 'Never'}</span><span>Last success: {heartbeat.last_success_at || 'Never'}</span><span>Last failure: {heartbeat.last_failure_at || 'Never'}</span><span>Next check: {heartbeat.next_scheduled_at || 'Not scheduled'}</span><span>Next retry: {heartbeat.next_retry_at || 'None'}</span></div>{['degraded', 'failed'].includes(heartbeat.status) && <p className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-destructive">⚠ Heartbeat degraded. Consecutive failures: {heartbeat.consecutive_failures}. Last successful heartbeat: {heartbeat.last_success_at || 'Never'}.</p>}<Button variant="outline" disabled={runningHeartbeat || !settings.heartbeat_enabled} onClick={() => void runNow()}>{runningHeartbeat ? 'Running…' : 'Run heartbeat now'}</Button></div>}</div>
      <Button onClick={() => void save()} disabled={saving}><Save className="mr-2 h-4 w-4" />{saving ? 'Saving...' : 'Save Settings'}</Button>
    </CardContent>
  </Card>;
}
