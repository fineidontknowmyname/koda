import { ButtonHTMLAttributes, forwardRef } from 'react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: 'primary' | 'secondary' | 'outline' | 'ghost';
    size?: 'sm' | 'md' | 'lg';
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
    ({ className, variant = 'primary', size = 'md', ...props }, ref) => {
        return (
            <button
                ref={ref}
                className={cn(
                    'inline-flex items-center justify-center rounded-lg font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none',
                    {
                        'bg-yellow-500 text-black hover:bg-yellow-400 focus:ring-yellow-500': variant === 'primary',
                        'bg-zinc-800 text-white hover:bg-zinc-700 focus:ring-zinc-500': variant === 'secondary',
                        'border border-zinc-700 bg-transparent hover:bg-zinc-800 text-white': variant === 'outline',
                        'bg-transparent hover:bg-zinc-800 text-white': variant === 'ghost',
                        'px-3 py-1.5 text-sm': size === 'sm',
                        'px-4 py-2 text-base': size === 'md',
                        'px-6 py-3 text-lg': size === 'lg',
                    },
                    className
                )}
                {...props}
            />
        );
    }
);
Button.displayName = 'Button';

export { Button };
