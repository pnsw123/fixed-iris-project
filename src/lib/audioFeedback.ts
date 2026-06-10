export class AudioFeedback {
    private ctx: AudioContext | null = null;
    private oscillator: OscillatorNode | null = null;
    private gainNode: GainNode | null = null;
    private isActive: boolean = false;
    private nextClickTime: number = 0;
    private currentDistanceScore: number = 0; // 0 (far) to 1 (perfect)
    private currentCenteringScore: number = 0; // 0 (off) to 1 (centered)

    private lastSpeakTime: number = 0;
    private lastMessage: string = '';

    constructor() {
        // AudioContext must be initialized after user interaction
    }

    async initialize() {
        this.isActive = true; // Set active immediately so TTS can work

        try {
            if (!this.ctx) {
                const AudioContextClass = window.AudioContext || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
                if (AudioContextClass) {
                    this.ctx = new AudioContextClass();
                    // Create master gain for volume control
                    this.gainNode = this.ctx.createGain();
                    this.gainNode.gain.value = 0.1; // Start low
                    this.gainNode.connect(this.ctx.destination);
                    this.scheduleClicks();
                }
            }
        } catch (e) {
            console.warn('[Audio] AudioContext init failed (user gesture needed?), but TTS might still work.', e);
        }

        // Warm up TTS
        this.speak('Ready');
    }

    // ... (existing scheduleClicks and playClick methods)

    // New TTS Method
    speak(text: string) {
        // TTS should work even if AudioContext (beeps) isn't ready
        if (typeof window === 'undefined') {
            return;
        }
        if (!window.speechSynthesis) {
            console.warn('[Audio] TTS not available (speechSynthesis undefined)');
            return;
        }

        const now = Date.now();
        // Throttle: Don't repeat the same message too often (3s)
        // Allow different messages sooner (1.5s)
        if (text === this.lastMessage && now - this.lastSpeakTime < 3000) return;
        if (now - this.lastSpeakTime < 1500) return;


        // Cancel pending speech to be responsive
        window.speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1.1; // Slightly faster
        utterance.pitch = 1.0;
        utterance.volume = 1.0;

        // iOS Safari fix: ensure voice is selected
        const voices = window.speechSynthesis.getVoices();
        if (voices.length > 0) {
            // Prefer English
            const enVoice = voices.find(v => v.lang.startsWith('en'));
            if (enVoice) utterance.voice = enVoice;
        }

        window.speechSynthesis.speak(utterance);

        this.lastSpeakTime = now;
        this.lastMessage = text;
    }

    // Main loop for the "Geiger Counter" effect
    private scheduleClicks() {
        if (!this.ctx || !this.isActive || !this.gainNode) return;

        // DISABLE CLICKS - User feedback: "Trash", "Just clicking sounds"
        // We rely on Voice + Haptics now.

        /* 
        const currentTime = this.ctx.currentTime;
        if (this.nextClickTime < currentTime) this.nextClickTime = currentTime;
        while (this.nextClickTime < currentTime + 0.5) {
            let interval = 0.5;
            if (this.currentDistanceScore > 0) interval = 0.5 - (this.currentDistanceScore * 0.45);
            this.playClick(this.nextClickTime);
            this.nextClickTime += interval;
        }
        */

        // Keep loop alive for haptics if we want them separate, 
        // but for now let's just loop to keep the engine running if needed.
        // Actually, we can stop the loop if we don't need clicks.
        // But let's keep it for potential haptic scheduling.

        requestAnimationFrame(() => this.scheduleClicks());
    }

    private playClick(_time: number) {
        // DISABLED
    }

    updateMetrics(distanceScore: number, centeringScore: number) {
        this.currentDistanceScore = Math.max(0, Math.min(1, distanceScore));
        this.currentCenteringScore = Math.max(0, Math.min(1, centeringScore));
    }

    async playSuccess() {
        if (!this.ctx || !this.gainNode) return;

        // Speak success
        this.speak('Perfect. Hold still.');

        const now = this.ctx.currentTime;

        // High-pitch success chime
        const osc = this.ctx.createOscillator();
        const env = this.ctx.createGain();

        osc.frequency.setValueAtTime(880, now); // A5
        osc.frequency.exponentialRampToValueAtTime(1760, now + 0.1); // A6

        env.connect(this.gainNode);
        osc.connect(env);

        env.gain.setValueAtTime(0, now);
        env.gain.linearRampToValueAtTime(1, now + 0.05);
        env.gain.exponentialRampToValueAtTime(0.01, now + 0.5);

        osc.start(now);
        osc.stop(now + 0.5);
    }

    stop() {
        this.isActive = false;
        if (this.ctx) {
            void this.ctx.close();
            this.ctx = null;
        }
        if (typeof window !== 'undefined' && window.speechSynthesis) {
            window.speechSynthesis.cancel();
        }
    }
}

// Export singleton
export const audioFeedback = new AudioFeedback();
