import { expect,it } from 'vitest';
import { exactMoney } from './format';
it('preserves large values without binary floating point conversion',()=>{
  expect(exactMoney('99999999999999999.99','USD')).toBe('USD 99999999999999999.99');
  expect(exactMoney('25.000000','JPY')).toBe('JPY 25');
  expect(exactMoney('25.120000','KWD')).toBe('KWD 25.120');
});
