
declare global {
    interface FileSystemDirectoryHandle {
        queryPermission(descriptor?: { mode?: 'read' | 'readwrite' }): Promise<'granted' | 'denied' | 'prompt'>;
        requestPermission(descriptor?: { mode?: 'read' | 'readwrite' }): Promise<'granted' | 'denied' | 'prompt'>;
    }
}

const DB_NAME = 'hukudok-storage';
const STORE_NAME = 'handles';
const KEY = 'output-directory';

export async function getStoredOutputDir(): Promise<FileSystemDirectoryHandle | null> {
    try {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, 1);

            request.onupgradeneeded = () => {
                request.result.createObjectStore(STORE_NAME);
            };

            request.onsuccess = () => {
                const db = request.result;
                const transaction = db.transaction(STORE_NAME, 'readonly');
                const store = transaction.objectStore(STORE_NAME);
                const getRequest = store.get(KEY);

                getRequest.onsuccess = () => {
                    resolve(getRequest.result || null);
                };

                getRequest.onerror = () => {
                    reject(getRequest.error);
                };
            };

            request.onerror = () => {
                reject(request.error);
            };
        });
    } catch (err) {
        console.error('Error getting output directory from IndexedDB:', err);
        return null;
    }
}

export async function setStoredOutputDir(handle: FileSystemDirectoryHandle): Promise<void> {
    try {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, 1);

            request.onupgradeneeded = () => {
                request.result.createObjectStore(STORE_NAME);
            };

            request.onsuccess = () => {
                const db = request.result;
                const transaction = db.transaction(STORE_NAME, 'readwrite');
                const store = transaction.objectStore(STORE_NAME);
                const putRequest = store.put(handle, KEY);

                putRequest.onsuccess = () => {
                    resolve();
                };

                putRequest.onerror = () => {
                    reject(putRequest.error);
                };
            };

            request.onerror = () => {
                reject(request.error);
            };
        });
    } catch (err) {
        console.error('Error saving output directory to IndexedDB:', err);
    }
}
