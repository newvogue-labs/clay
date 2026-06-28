import '@testing-library/jest-dom'
import { beforeEach, vi } from 'vitest'

// --- localStorage mock (jsdom 20+ не предоставляет его по умолчанию) ---
// Полноценная in-memory реализация: App.tsx делает getItem→...→setItem,
// поэтому нужен рабочий store, а не заглушки, возвращающие undefined.
class LocalStorageMock implements Storage {
	private store = new Map<string, string>()

	get length(): number {
		return this.store.size
	}

	clear(): void {
		this.store.clear()
	}

	getItem(key: string): string | null {
		return this.store.has(key) ? (this.store.get(key) as string) : null
	}

	key(index: number): string | null {
		return Array.from(this.store.keys())[index] ?? null
	}

	removeItem(key: string): void {
		this.store.delete(key)
	}

	setItem(key: string, value: string): void {
		this.store.set(key, String(value))
	}
}

Object.defineProperty(window, 'localStorage', {
	value: new LocalStorageMock(),
	writable: true,
	configurable: true,
})

// --- matchMedia stub (на будущее: theme/responsive-хуки; сейчас App.tsx не использует) ---
Object.defineProperty(window, 'matchMedia', {
	writable: true,
	configurable: true,
	value: (query: string): MediaQueryList =>
		({
			matches: false,
			media: query,
			onchange: null,
			addListener: vi.fn(), // deprecated, для старых либ
			removeListener: vi.fn(), // deprecated
			addEventListener: vi.fn(),
			removeEventListener: vi.fn(),
			dispatchEvent: vi.fn(),
		}) as unknown as MediaQueryList,
})

// сброс persisted-состояния между тестами — без протечки между кейсами
beforeEach(() => {
	window.localStorage.clear()
})
