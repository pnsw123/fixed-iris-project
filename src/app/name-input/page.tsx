'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { motion } from 'motion/react';
import AppHeader from '@/components/AppHeader';
import SpotlightBackground from '@/components/SpotlightBackground';

const MAX_NAME_LENGTH = 40;

export default function NameInputPage() {
    const router = useRouter();
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [isNavigating, setIsNavigating] = useState(false);

    const handleStartCapture = async () => {
        if (!firstName.trim() || !lastName.trim()) return;

        setIsNavigating(true);

        try {
            // Save to sessionStorage
            const userData = {
                firstName: firstName.trim(),
                lastName: lastName.trim(),
            };

            sessionStorage.setItem('heritage_user', JSON.stringify(userData));
            router.push('/capture');
        } catch (error) {
            console.error('[NameInput] Navigation error:', error);
            setIsNavigating(false);
        }
    };

    const canContinue = firstName.trim().length > 0 && lastName.trim().length > 0;

    const firstNameTooShort = firstName.length > 0 && firstName.trim().length < 2;
    const lastNameTooShort = lastName.length > 0 && lastName.trim().length < 2;

    return (
        <div className="min-h-screen bg-black flex flex-col text-white relative overflow-hidden">
            <SpotlightBackground color="rgba(52, 211, 153, 0.20)" />

            {/* Header */}
            <AppHeader title="IDENTITY" showBack />

            {/* Main Content */}
            <div className="flex-1 px-6 py-12 max-w-lg mx-auto w-full relative z-10">
                <motion.div
                    className="space-y-8"
                    initial={{ opacity: 0, y: 24 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.55, ease: [0.25, 0.46, 0.45, 0.94] }}
                >
                    <div className="space-y-2">
                        <h1 className="text-3xl font-light tracking-tight">Enter Your Name</h1>
                        <p className="text-gray-400 font-light">
                            Your name will be displayed on your heritage card.
                        </p>
                    </div>

                    <div className="space-y-6">
                        {/* First Name */}
                        <div className="space-y-2">
                            <div className="flex items-center justify-between">
                                <label className="text-xs font-mono text-gray-500 uppercase tracking-wider">
                                    First Name
                                </label>
                                {firstName.length > 0 && (
                                    <span className={`text-xs font-mono tabular-nums transition-colors ${firstName.length >= MAX_NAME_LENGTH ? 'text-red-400' : 'text-gray-600'}`}>
                                        {firstName.length}/{MAX_NAME_LENGTH}
                                    </span>
                                )}
                            </div>
                            <input
                                type="text"
                                value={firstName}
                                onChange={(e) => setFirstName(e.target.value)}
                                maxLength={MAX_NAME_LENGTH}
                                className="w-full bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500/50 transition-colors"
                                placeholder="Enter first name"
                                dir="auto"
                            />
                            {firstNameTooShort && (
                                <p className="text-xs text-red-400 font-light">Name must be at least 2 characters.</p>
                            )}
                        </div>

                        {/* Last Name */}
                        <div className="space-y-2">
                            <div className="flex items-center justify-between">
                                <label className="text-xs font-mono text-gray-500 uppercase tracking-wider">
                                    Last Name
                                </label>
                                {lastName.length > 0 && (
                                    <span className={`text-xs font-mono tabular-nums transition-colors ${lastName.length >= MAX_NAME_LENGTH ? 'text-red-400' : 'text-gray-600'}`}>
                                        {lastName.length}/{MAX_NAME_LENGTH}
                                    </span>
                                )}
                            </div>
                            <input
                                type="text"
                                value={lastName}
                                onChange={(e) => setLastName(e.target.value)}
                                maxLength={MAX_NAME_LENGTH}
                                className="w-full bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500/50 transition-colors"
                                placeholder="Enter last name"
                                dir="auto"
                            />
                            {lastNameTooShort && (
                                <p className="text-xs text-red-400 font-light">Name must be at least 2 characters.</p>
                            )}
                        </div>
                    </div>

                    {/* CTA */}
                    <div className="pt-4">
                        <button
                            onClick={() => { void handleStartCapture(); }}
                            disabled={!canContinue || isNavigating || firstNameTooShort || lastNameTooShort}
                            className={`w-full font-medium text-base py-4 px-6 transition-colors flex items-center justify-center gap-2 ${canContinue && !isNavigating && !firstNameTooShort && !lastNameTooShort
                                ? 'bg-white text-black hover:bg-gray-100'
                                : 'bg-gray-800 text-gray-500 cursor-not-allowed'
                                }`}
                        >
                            {isNavigating ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    Loading...
                                </>
                            ) : (
                                'Start Capture'
                            )}
                        </button>
                    </div>
                </motion.div>
            </div>
        </div>
    );
}
