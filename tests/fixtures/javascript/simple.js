const util = require('./esm.js');

class Person {
  constructor(n) {
    this.name = n;
  }

  hi() {
    return util.foo();
  }
}

const arrow = (x) => x + 1;

function standalone() {
  return arrow(2);
}
