`timescale 1ns/1ps

module mux_2to1_tb;

    logic a;
    logic b;
    logic select;
    logic y;

    mux_2to1 dut (
        .a(a),
        .b(b),
        .select(select),
        .y(y)
    );

    initial begin
        $display("Starting 2:1 MUX test");

        a = 0;
        b = 1;
        select = 0;
        #10;

        if (y !== 0)
            $display("FAIL: Expected y=0, got y=%b", y);
        else
            $display("PASS: Test 1");

        select = 1;
        #10;

        if (y !== 1)
            $display("FAIL: Expected y=1, got y=%b", y);
        else
            $display("PASS: Test 2");

        a = 1;
        b = 0;
        select = 0;
        #10;

        if (y !== 1)
            $display("FAIL: Expected y=1, got y=%b", y);
        else
            $display("PASS: Test 3");

        select = 1;
        #10;

        if (y !== 0)
            $display("FAIL: Expected y=0, got y=%b", y);
        else
            $display("PASS: Test 4");

        $display("MUX testing complete");
        $finish;
    end

endmodule