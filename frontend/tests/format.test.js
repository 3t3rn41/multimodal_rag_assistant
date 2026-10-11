import {describe,expect,it} from 'vitest';
import {fmtPercent} from '../src/utils/format';
describe('percentage display',()=>{
 it.each([[53.61702127659574,'53.62%'],[1.0051,'1.01%'],[100,'100.00%'],[0,'0.00%'],
  [-1,'0.00%'],[101,'100.00%'],[NaN,'0.00%'],[Infinity,'0.00%'],[undefined,'0.00%']])(
  'formats %s as %s',(value,expected)=>expect(fmtPercent(value)).toBe(expected));
});
