import 'react-native-url-polyfill/auto';
import 'react-native-get-random-values';
import * as Random from 'expo-random';

declare global {
  interface Crypto {
    getRandomValues<T extends ArrayBufferView | null>(array: T): T;
  }
}

if (typeof globalThis.crypto === 'undefined') {
  (globalThis as any).crypto = {};
}

if (typeof globalThis.crypto.getRandomValues !== 'function') {
  (globalThis.crypto as any).getRandomValues = (arr: Uint8Array) => {
    const bytes = Random.getRandomBytes(arr.length);
    arr.set(bytes);
    return arr;
  };
}

console.log(
  'crypto.getRandomValues ready?',
  typeof globalThis.crypto?.getRandomValues === 'function'
);
