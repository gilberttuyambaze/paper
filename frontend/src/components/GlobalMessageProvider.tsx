import { useEffect, useState } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, HelpCircle, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { type GlobalMessage, registerMessagePublisher } from '@/lib/messages';

const presentation = {
  success: { title: 'Success', icon: CheckCircle2, tone: 'border-success/50 bg-success-soft/30 text-success' },
  error: { title: 'Something went wrong', icon: AlertCircle, tone: 'border-error/50 bg-error-soft/30 text-error' },
  warning: { title: 'Warning', icon: AlertTriangle, tone: 'border-warning-border bg-warning-soft/30 text-warning-foreground' },
  info: { title: 'Information', icon: Info, tone: 'border-info/50 bg-info-soft/30 text-info' },
  confirmation: { title: 'Please confirm', icon: HelpCircle, tone: 'border-warning-border bg-warning-soft/30 text-warning-foreground' },
} as const;

export default function GlobalMessageProvider() {
  const [message, setMessage] = useState<GlobalMessage | null>(null);

  useEffect(() => {
    registerMessagePublisher(setMessage);
    return () => registerMessagePublisher(null);
  }, []);

  const close = () => setMessage(null);
  const canDismiss = message?.dismissible !== false;
  const config = message ? presentation[message.type] : presentation.info;
  const Icon = config.icon;
  const actions = message?.actions?.length ? message.actions : [{ label: 'OK', onClick: close }];

  return (
    <Dialog open={Boolean(message)} onOpenChange={(open) => !open && canDismiss && close()}>
      <DialogContent className={`w-[calc(100vw-2rem)] max-w-md overflow-hidden border p-0 shadow-2xl ${config.tone}`}>
        {message && <div className="bg-background/90 p-6 text-center backdrop-blur-sm sm:p-8">
          <div className={`mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full border bg-background/70 shadow-lg ${config.tone}`}>
            <Icon className="h-8 w-8" aria-hidden="true" />
          </div>
          <DialogHeader className="items-center text-center">
            <DialogTitle className="theme-title text-xl">{message.title || config.title}</DialogTitle>
            <DialogDescription className="theme-muted max-w-sm pt-2 text-sm leading-6">{message.message}</DialogDescription>
          </DialogHeader>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
            {actions.map((action, index) => <Button key={`${action.label}-${index}`} variant={action.variant || (message.type === 'error' ? 'outline' : 'default')} onClick={async () => { await action.onClick(); close(); }}>{action.label}</Button>)}
          </div>
        </div>}
      </DialogContent>
    </Dialog>
  );
}
