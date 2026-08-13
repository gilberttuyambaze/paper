import { cn } from '@/lib/utils';

export default function AcademicAiMark({ className }: { className?: string }) {
  return <img src="/assets/icons/paper-hub-ai.svg" alt="" aria-hidden="true" className={cn('h-10 w-10', className)} />;
}
