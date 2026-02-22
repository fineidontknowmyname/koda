import { LabelHTMLAttributes, forwardRef } from 'react';
import { cn } from '@/components/ui/Button';

const Label = forwardRef<HTMLLabelElement, LabelHTMLAttributes<HTMLLabelElement>>(
    ({ className, ...props }, ref) => (
        <label
            ref={ref}
            className={cn(
                "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 text-zinc-300",
                className
            )}
            {...props}
        />
    )
);
Label.displayName = "Label";

export { Label };
