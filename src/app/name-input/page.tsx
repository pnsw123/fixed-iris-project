'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Loader2 } from 'lucide-react';

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

    return (
        <div className="min-h-screen bg-black flex flex-col text-white">
            {/* Header */}
            <div className="px-6 py-6">
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => router.back()}
                        className="p-2 -ml-2 hover:bg-gray-900 rounded-full transition-colors"
                    >
                        <ArrowLeft className="w-5 h-5 text-gray-400" />
                    </button>
                    <span className="text-sm font-mono text-gray-400 tracking-wider">IDENTITY</span>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 px-8 py-16 sm:px-16 max-w-xl mx-auto w-full">
                <div className="space-y-8">
                    <div className="space-y-2">
                        <h1 className="text-3xl font-light tracking-tight">Enter Your Name</h1>
                        <p className="text-gray-400 font-light">
                            Your name will be displayed on your heritage card.
                        </p>
                    </div>

                    <div className="space-y-6">
                        {/* First Name */}
                        <div className="space-y-2">
                            <label className="text-xs font-mono text-gray-500 uppercase tracking-wider">
                                First Name
                            </label>
                            <input
                                type="text"
                                value={firstName}
                                onChange={(e) => setFirstName(e.target.value)}
                                className="w-full bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-gray-600 transition-colors"
                                placeholder="Enter first name"
                                dir="auto"
                            />
                        </div>

                        {/* Last Name */}
                        <div className="space-y-2">
                            <label className="text-xs font-mono text-gray-500 uppercase tracking-wider">
                                Last Name
                            </label>
                            <input
                                type="text"
                                value={lastName}
                                onChange={(e) => setLastName(e.target.value)}
                                className="w-full bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-gray-600 transition-colors"
                                placeholder="Enter last name"
                                dir="auto"
                            />
                        </div>
                    </div>

                    {/* CTA */}
                    <div className="pt-4">
                        <button
                            onClick={handleStartCapture}
                            disabled={!canContinue || isNavigating}
                            className={`w-full font-medium text-base py-4 px-6 transition-colors flex items-center justify-center gap-2 ${canContinue && !isNavigating
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
                </div>
            </div>
        </div>
    );
}
