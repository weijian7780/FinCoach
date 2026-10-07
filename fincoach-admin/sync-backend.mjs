// Ship the compiled website with the existing Python image, without Node at runtime.
import { cp, mkdir } from 'node:fs/promises';
const destination = new URL('../fincoach-backend/admin-static/', import.meta.url);
await mkdir(destination, { recursive: true });
await cp(new URL('./dist/', import.meta.url), destination, { recursive: true });
