'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, CheckCircle2, Loader2 } from 'lucide-react';

// Debounce utility
function useDebounce<T>(value: T, delay: number): T {
    const [debouncedValue, setDebouncedValue] = useState<T>(value);
    useEffect(() => {
        const handler = setTimeout(() => setDebouncedValue(value), delay);
        return () => clearTimeout(handler);
    }, [value, delay]);
    return debouncedValue;
}

export default function NameInputPage() {
    const router = useRouter();
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [tribeMatch, setTribeMatch] = useState<any>(null);
    const [isMatching, setIsMatching] = useState(false);

    const debouncedLastName = useDebounce(lastName, 500);
    const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'https://localhost:8000';

    useEffect(() => {
        if (debouncedLastName.length < 2) {
            setTribeMatch(null);
            return;
        }

        const fetchMatch = async () => {
            setIsMatching(true);
            try {
                const res = await fetch(`${BACKEND_URL}/api/v1/tribes/match`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: debouncedLastName })
                });
                const data = await res.json();
                if (data.success && data.match) {
                    setTribeMatch(data.match);
                } else {
                    setTribeMatch(null);
                }
            } catch (e) {
                console.error('Match failed', e);
            } finally {
                setIsMatching(false);
            }
        };
        fetchMatch();
    }, [debouncedLastName, BACKEND_URL]);

    const handleStartCapture = () => {
        if (!firstName.trim() || !lastName.trim()) return;

        sessionStorage.setItem('heritage_user', JSON.stringify({
            firstName: firstName.trim(),
            lastName: lastName.trim(),
            tribe: tribeMatch
        }));

        router.push('/capture');
    };

    const canContinue = firstName.trim().length > 0 && lastName.trim().length > 0;

    return (
        <div className="min-h-screen bg-black flex flex-col text-white">
            {/* Header */}
            <div className="border-b border-gray-800 px-6 py-4">
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
            <div className="flex-1 px-6 py-12 max-w-lg mx-auto w-full">
                <div className="space-y-8">
                    <div className="space-y-2">
                        <h1 className="text-3xl font-light tracking-tight">Enter Your Name</h1>
                        <p className="text-gray-400 font-light">
                            We'll match your family name to our tribal database.
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
                                Family Name
                            </label>
                            <div className="relative">
                                <input
                                    type="text"
                                    value={lastName}
                                    onChange={(e) => setLastName(e.target.value)}
                                    className="w-full bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-gray-600 transition-colors"
                                    placeholder="Enter family name"
                                    dir="auto"
                                />
                                {isMatching && (
                                    <div className="absolute right-3 top-1/2 -translate-y-1/2">
                                        <Loader2 className="w-4 h-4 text-gray-500 animate-spin" />
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Tribe Match Result */}
                        {tribeMatch && (
                            <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-4 animate-in fade-in slide-in-from-bottom-2">
                                <div className="flex items-start gap-3">
                                    <CheckCircle2 className="w-5 h-5 text-green-500 mt-0.5" />
                                    <div>
                                        <p className="text-sm text-gray-300">
                                            Tribal match found:
                                        </p>
                                        <p className="text-lg font-medium text-white mt-1" dir="rtl">
                                            قبيلة {tribeMatch.canonical_name}
                                        </p>
                                        <p className="text-xs text-gray-500 mt-1 font-mono">
                                            Confidence: {tribeMatch.confidence}%
                                        </p>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* CTA */}
                    <div className="pt-4">
                        <button
                            onClick={handleStartCapture}
                            disabled={!canContinue}
                            className={`w-full font-medium text-base py-4 px-6 transition-colors ${canContinue
                                    ? 'bg-white text-black hover:bg-gray-100'
                                    : 'bg-gray-800 text-gray-500 cursor-not-allowed'
                                }`}
                        >
                            Start Capture
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
