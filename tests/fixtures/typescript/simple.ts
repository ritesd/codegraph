export interface IShape {
  area(): number;
}

export class Square implements IShape {
  constructor(private side: number) {}

  area(): number {
    return this.side * this.side;
  }
}
