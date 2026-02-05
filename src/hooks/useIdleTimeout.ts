import { useEffect, useRef, useState } from 'react';
import { useMsal } from '@azure/msal-react';
import { toast } from 'sonner';

/**
 * Idle Timeout Hook
 * 
 * Automatically logs out the user after a period of inactivity.
 * Tracks user activity (mouse, keyboard, touch) and resets the timer.
 * 
 * @param timeoutMinutes - Idle timeout duration in minutes (default: 30)
 * @param warningMinutes - Show warning before logout (default: 5 minutes before)
 */
export const useIdleTimeout = (timeoutMinutes: number = 30, warningMinutes: number = 5) => {
    const { instance } = useMsal();
    const timeoutId = useRef<NodeJS.Timeout | null>(null);
    const warningId = useRef<NodeJS.Timeout | null>(null);
    const [showWarning, setShowWarning] = useState(false);

    const TIMEOUT_MS = timeoutMinutes * 60 * 1000; // Convert minutes to milliseconds
    const WARNING_MS = (timeoutMinutes - warningMinutes) * 60 * 1000;

    const logout = () => {
        console.log('🔒 Idle timeout - Logging out user');
        toast.error('Oturum zaman aşımı', {
            description: 'Uzun süre işlem yapmadığınız için güvenlik nedeniyle çıkış yapıldı.',
            duration: 5000,
        });

        // Clear any existing timers
        if (timeoutId.current) clearTimeout(timeoutId.current);
        if (warningId.current) clearTimeout(warningId.current);

        // Logout and redirect to login
        instance.logoutRedirect({
            postLogoutRedirectUri: window.location.origin + '/#/login',
        });
    };

    const showWarningToast = () => {
        console.log('⚠️ Idle warning - User will be logged out soon');
        setShowWarning(true);
        toast.warning('Oturum sona erecek', {
            description: `${warningMinutes} dakika içinde işlem yapmazsanız otomatik çıkış yapılacak.`,
            duration: (warningMinutes * 60 * 1000), // Show for remaining time
            action: {
                label: 'Devam Et',
                onClick: () => {
                    setShowWarning(false);
                    resetTimer(); // Reset on user action
                },
            },
        });
    };

    const resetTimer = () => {
        // Clear existing timers
        if (timeoutId.current) clearTimeout(timeoutId.current);
        if (warningId.current) clearTimeout(warningId.current);
        setShowWarning(false);

        // Set warning timer (show warning X minutes before logout)
        warningId.current = setTimeout(showWarningToast, WARNING_MS);

        // Set logout timer
        timeoutId.current = setTimeout(logout, TIMEOUT_MS);
    };

    useEffect(() => {
        // Events that indicate user activity
        const events = [
            'mousedown',
            'mousemove',
            'keypress',
            'scroll',
            'touchstart',
            'click',
        ];

        // Reset timer on any user activity
        const handleActivity = () => {
            resetTimer();
        };

        // Initialize timer
        resetTimer();

        // Add event listeners
        events.forEach((event) => {
            window.addEventListener(event, handleActivity);
        });

        // Cleanup on unmount
        return () => {
            if (timeoutId.current) clearTimeout(timeoutId.current);
            if (warningId.current) clearTimeout(warningId.current);
            events.forEach((event) => {
                window.removeEventListener(event, handleActivity);
            });
        };
    }, [instance, TIMEOUT_MS, WARNING_MS]);

    return { showWarning, resetTimer };
};
