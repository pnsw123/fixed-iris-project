#!/usr/bin/env node

/**
 * Script to inspect ONNX model metadata
 * This helps us understand the correct input/output tensor shapes and names
 */

import * as ort from 'onnxruntime-node';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function inspectModel() {
    try {
        const modelPath = join(__dirname, '../public/models/esrgan.onnx');
        console.log('Loading ONNX model from:', modelPath);

        const session = await ort.InferenceSession.create(modelPath);

        console.log('\n=== MODEL METADATA ===\n');

        console.log('Input Names:', session.inputNames);
        console.log('Output Names:', session.outputNames);

        console.log('\n=== INPUT DETAILS ===\n');
        session.inputNames.forEach(name => {
            const input = session.inputMetadata[name];
            console.log(`Input: ${name}`);
            console.log(`  Shape: ${JSON.stringify(input.dims)}`);
            console.log(`  Type: ${input.type}`);
        });

        console.log('\n=== OUTPUT DETAILS ===\n');
        session.outputNames.forEach(name => {
            const output = session.outputMetadata[name];
            console.log(`Output: ${name}`);
            console.log(`  Shape: ${JSON.stringify(output.dims)}`);
            console.log(`  Type: ${output.type}`);
        });

        console.log('\n=== RECOMMENDATIONS ===\n');
        const inputShape = session.inputMetadata[session.inputNames[0]].dims;
        const outputShape = session.outputMetadata[session.outputNames[0]].dims;

        console.log('Based on the model metadata:');
        console.log(`1. Input tensor name: "${session.inputNames[0]}"`);
        console.log(`2. Input shape: ${JSON.stringify(inputShape)}`);
        console.log(`3. Output tensor name: "${session.outputNames[0]}"`);
        console.log(`4. Output shape: ${JSON.stringify(outputShape)}`);

        if (inputShape[1] === 3) {
            console.log('5. Channel format: CHW (Channels, Height, Width)');
        } else if (inputShape[3] === 3) {
            console.log('5. Channel format: HWC (Height, Width, Channels)');
        }

        console.log('\nNote: Typical ESRGAN normalization is [0, 1] for input and output.');

    } catch (error) {
        console.error('Error inspecting model:', error);
        process.exit(1);
    }
}

inspectModel();
