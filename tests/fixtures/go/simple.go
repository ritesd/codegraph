package main

import "fmt"

type Point struct {
	X, Y int
}

func (p Point) Len() int {
	return p.X + p.Y
}

func Add(a, b int) int {
	return a + b
}

func main() {
	p := Point{1, 2}
	fmt.Println(p.Len(), Add(1, 2))
}
