package com.example;

import java.util.List;

public class Main {
    public Main() {}

    public static void main(String[] args) {
        Util.echo("x");
    }
}

interface Util {
    static void echo(String s) {
        System.out.println(s);
    }
}

enum Color {
    RED,
    GREEN,
    BLUE;

    public String lower() {
        return name().toLowerCase();
    }
}
