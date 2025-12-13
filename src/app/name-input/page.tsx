'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, CheckCircle2, Loader2 } from 'lucide-react';

// Type for tribe match result
interface TribeMatch {
    tribe_id: string;
    canonical_name: string;
    hierarchy_path: string;
    confidence: number;
    match_type: string;
}

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
    const [tribeMatch, setTribeMatch] = useState<TribeMatch | null>(null);
    const [isMatching, setIsMatching] = useState(false);
    const [isNavigating, setIsNavigating] = useState(false);

    // KEY FIX: Store reference to pending API promise
    const pendingPromiseRef = useRef<Promise<TribeMatch | null> | null>(null);
    const abortControllerRef = useRef<AbortController | null>(null);

    const debouncedLastName = useDebounce(lastName, 500);
    const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'https://localhost:8000';

    useEffect(() => {
        if (debouncedLastName.length < 2) {
            setTribeMatch(null);
            pendingPromiseRef.current = null;
            return;
        }

        // Cancel previous request
        abortControllerRef.current?.abort();
        abortControllerRef.current = new AbortController();

        setIsMatching(true);

        // Create the promise and store it in ref
        const promise = fetch(`${BACKEND_URL}/api/v1/tribes/match`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: debouncedLastName, confidence_threshold: 95 }),
            signal: abortControllerRef.current.signal,
        })
            .then(res => res.json())
            .then(data => {
                console.log('[NameInput] 🔍 API response:', data);
                if (data.success && data.match && data.match.confidence >= 95) {
                    console.log('[NameInput] ✅ Match:', data.match.canonical_name);
                    console.log('[NameInput] 📍 hierarchy_path:', data.match.hierarchy_path);
                    setTribeMatch(data.match);
                    return data.match as TribeMatch;
                } else {
                    console.log('[NameInput] ❌ No match or below 95% confidence');
                    setTribeMatch(null);
                    return null;
                }
            })
            .catch(err => {
                if (err.name !== 'AbortError') {
                    console.error('[NameInput] Match failed:', err);
                }
                return null;
            })
            .finally(() => {
                if (!abortControllerRef.current?.signal.aborted) {
                    setIsMatching(false);
                }
            });

        // Store promise reference for handleStartCapture to await
        pendingPromiseRef.current = promise;

        // Cleanup
        return () => {
            abortControllerRef.current?.abort();
        };
    }, [debouncedLastName, BACKEND_URL]);

    // KEY FIX: Async handler that awaits pending API before navigation
    const handleStartCapture = async () => {
        if (!firstName.trim() || !lastName.trim()) return;

        setIsNavigating(true);

        try {
            // If request is still pending, wait for it to complete
            let finalTribeMatch = tribeMatch;
            if (pendingPromiseRef.current) {
                console.log('[NameInput] ⏳ Waiting for pending API request...');
                finalTribeMatch = await pendingPromiseRef.current;
                console.log('[NameInput] ✅ API complete, got:', finalTribeMatch?.hierarchy_path);
            }

            // Save to sessionStorage with guaranteed data
            const userData = {
                firstName: firstName.trim(),
                lastName: lastName.trim(),
                tribe: finalTribeMatch
            };

            console.log('[NameInput] 💾 Saving to sessionStorage:', userData);
            sessionStorage.setItem('heritage_user', JSON.stringify(userData));

            router.push('/capture');
        } catch (error) {
            console.error('[NameInput] Navigation error:', error);
            setIsNavigating(false);
        }
    };

    const canContinue = firstName.trim().length > 0 && lastName.trim().length > 0;
    const isLoading = isMatching || isNavigating;

    return (
        <div className="min-h-screen bg-black flex flex-col text-white">
            {/* DEBUG PANEL - Remove after fixing */}
            <div className="bg-blue-900/50 border border-blue-500 p-3 text-xs font-mono text-white overflow-auto max-h-40">
                <p className="text-blue-400 font-bold mb-1">🔧 NAME-INPUT DEBUG:</p>
                <p>tribeMatch: {tribeMatch ? 'EXISTS' : 'NULL'}</p>
                <p>hierarchy_path: {tribeMatch?.hierarchy_path || 'null'}</p>
                <p>canonical_name: {tribeMatch?.canonical_name || 'null'}</p>
                <p>pendingPromise: {pendingPromiseRef.current ? 'PENDING' : 'none'}</p>
                <p>isMatching: {isMatching ? 'YES' : 'NO'}</p>
            </div>

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
                                        {tribeMatch.hierarchy_path && (
                                            <p className="text-sm text-emerald-400/80 mt-1" dir="rtl">
                                                {tribeMatch.hierarchy_path}
                                            </p>
                                        )}
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
                            disabled={!canContinue || isLoading}
                            className={`w-full font-medium text-base py-4 px-6 transition-colors flex items-center justify-center gap-2 ${canContinue && !isLoading
                                ? 'bg-white text-black hover:bg-gray-100'
                                : 'bg-gray-800 text-gray-500 cursor-not-allowed'
                                }`}
                        >
                            {isNavigating ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    جاري البحث...
                                </>
                            ) : isMatching ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    Matching...
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

