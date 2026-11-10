import { describe, expect, it } from 'vitest';
import { errorMessage } from './api';
describe('action errors',()=>{
  it('preserves concrete errors',()=>expect(errorMessage(new Error('Validation failed'))).toBe('Validation failed'));
  it('handles unknown errors',()=>expect(errorMessage(null)).toBe('Operation failed'));
});
