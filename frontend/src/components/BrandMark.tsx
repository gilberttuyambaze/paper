import { cn } from '@/lib/utils';

interface BrandMarkProps {
  className?: string;
  imageClassName?: string;
  label?: boolean;
  labelClassName?: string;
}

export default function BrandMark({
  className,
  imageClassName,
  label = false,
  labelClassName,
}: BrandMarkProps) {
  return (
    <span className={cn('flex items-center gap-3', className)}>
      <img
        src="/favicon.svg"
        alt="UR Academic Resource Hub logo"
        className={cn('h-10 w-10 object-contain', imageClassName)}
      />
      {label && <span className={cn('font-bold', labelClassName)}>UR Academic Resource Hub</span>}
    </span>
  );
}
