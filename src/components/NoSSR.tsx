'use client';

import React, { useState, useEffect } from 'react';

const NoSSR = ({ children }: { children: React.ReactNode }) => {
    const [isMounted, setIsMounted] = useState(false);

    useEffect(() => {
        const timer = setTimeout(() => setIsMounted(true), 0);
        return () => clearTimeout(timer);
    }, []);

    if (!isMounted) {
        return null;
    }

    return <>{children}</>;
};

export default NoSSR;
