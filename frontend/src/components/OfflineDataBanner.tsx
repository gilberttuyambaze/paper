import { WifiOff } from 'lucide-react';

interface OfflineDataBannerProps {
  message?: string;
}

export default function OfflineDataBanner({
  message = 'You are viewing cached data because live updates are currently unavailable.',
}: OfflineDataBannerProps) {
  return (
    <div className="mb-6 rounded-xl border border-primary/35 bg-primary/10 px-4 py-3 text-sm text-foreground">
      <div className="flex items-start gap-3">
        <WifiOff className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <p>{message}</p>
      </div>
    </div>
  );
}
