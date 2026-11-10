export function exactMoney(amount:string,currency:string):string {
  const digits=new Intl.NumberFormat('en',{style:'currency',currency}).resolvedOptions().maximumFractionDigits??2;
  const [whole,fraction='']=amount.split('.');
  const significant=fraction.replace(/0+$/,'');
  const width=Math.max(digits,significant.length);
  return `${currency} ${whole}${width?'.'+significant.padEnd(width,'0'):''}`;
}
