import type { ReactNode } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';

type AdminDetailDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
};

/**
 * The common, responsive detail surface used by Admin management records.
 * Radix supplies the modal focus trap, Escape handling, and focus restoration.
 */
export default function AdminDetailDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
}: AdminDetailDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-1rem)] w-[calc(100vw-1rem)] max-w-4xl overflow-y-auto p-4 sm:max-h-[90vh] sm:w-full sm:p-6">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  );
}
