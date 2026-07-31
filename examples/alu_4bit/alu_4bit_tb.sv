`timescale 1ns/1ps

module alu_4bit_tb;

    logic [3:0] a;
    logic [3:0] b;
    logic [1:0] opcode;

    logic [3:0] result;
    logic       carry;
    logic       zero;

    integer passed_tests;
    integer failed_tests;

    alu_4bit dut (
        .a(a),
        .b(b),
        .opcode(opcode),
        .result(result),
        .carry(carry),
        .zero(zero)
    );

    initial begin
        $dumpfile("examples/alu_4bit/alu_4bit.vcd");
        $dumpvars(0, alu_4bit_tb);

        passed_tests = 0;
        failed_tests = 0;

        $display("Starting 4-bit ALU tests");

        // Test 1: 3 + 2 = 5
        a = 4'd3;
        b = 4'd2;
        opcode = 2'b00;
        #10;

        if (result === 4'd5 && carry === 1'b0 && zero === 1'b0) begin
            $display("PASS: Test 1 - ADD without carry");
            passed_tests = passed_tests + 1;
        end
        else begin
            $display(
                "FAIL: Test 1 - Expected result=5 carry=0 zero=0, got result=%d carry=%b zero=%b",
                result,
                carry,
                zero
            );
            failed_tests = failed_tests + 1;
        end

        // Test 2: 15 + 1 = 16
        // 4-bit result wraps to 0 and carry becomes 1
        a = 4'd15;
        b = 4'd1;
        opcode = 2'b00;
        #10;

        if (result === 4'd0 && carry === 1'b1 && zero === 1'b1) begin
            $display("PASS: Test 2 - ADD with carry");
            passed_tests = passed_tests + 1;
        end
        else begin
            $display(
                "FAIL: Test 2 - Expected result=0 carry=1 zero=1, got result=%d carry=%b zero=%b",
                result,
                carry,
                zero
            );
            failed_tests = failed_tests + 1;
        end

        // Test 3: 7 - 3 = 4
        a = 4'd7;
        b = 4'd3;
        opcode = 2'b01;
        #10;

        if (result === 4'd4 && carry === 1'b0 && zero === 1'b0) begin
            $display("PASS: Test 3 - SUBTRACT");
            passed_tests = passed_tests + 1;
        end
        else begin
            $display(
                "FAIL: Test 3 - Expected result=4 carry=0 zero=0, got result=%d carry=%b zero=%b",
                result,
                carry,
                zero
            );
            failed_tests = failed_tests + 1;
        end

        // Test 4: 3 - 5 wraps to 14 in 4-bit unsigned arithmetic
        a = 4'd3;
        b = 4'd5;
        opcode = 2'b01;
        #10;

        if (result === 4'd14 && carry === 1'b0 && zero === 1'b0) begin
            $display("PASS: Test 4 - SUBTRACT with wraparound");
            passed_tests = passed_tests + 1;
        end
        else begin
            $display(
                "FAIL: Test 4 - Expected result=14 carry=0 zero=0, got result=%d carry=%b zero=%b",
                result,
                carry,
                zero
            );
            failed_tests = failed_tests + 1;
        end

        // Test 5: 1100 AND 1010 = 1000
        a = 4'b1100;
        b = 4'b1010;
        opcode = 2'b10;
        #10;

        if (result === 4'b1000 && carry === 1'b0 && zero === 1'b0) begin
            $display("PASS: Test 5 - AND");
            passed_tests = passed_tests + 1;
        end
        else begin
            $display(
                "FAIL: Test 5 - Expected result=1000 carry=0 zero=0, got result=%b carry=%b zero=%b",
                result,
                carry,
                zero
            );
            failed_tests = failed_tests + 1;
        end

        // Test 6: 1100 OR 1010 = 1110
        a = 4'b1100;
        b = 4'b1010;
        opcode = 2'b11;
        #10;

        if (result === 4'b1110 && carry === 1'b0 && zero === 1'b0) begin
            $display("PASS: Test 6 - OR");
            passed_tests = passed_tests + 1;
        end
        else begin
            $display(
                "FAIL: Test 6 - Expected result=1110 carry=0 zero=0, got result=%b carry=%b zero=%b",
                result,
                carry,
                zero
            );
            failed_tests = failed_tests + 1;
        end

        // Test 7: 5 - 5 = 0, so zero must be 1
        a = 4'd5;
        b = 4'd5;
        opcode = 2'b01;
        #10;

        if (result === 4'd0 && carry === 1'b0 && zero === 1'b1) begin
            $display("PASS: Test 7 - Zero flag");
            passed_tests = passed_tests + 1;
        end
        else begin
            $display(
                "FAIL: Test 7 - Expected result=0 carry=0 zero=1, got result=%d carry=%b zero=%b",
                result,
                carry,
                zero
            );
            failed_tests = failed_tests + 1;
        end

        $display("--------------------------------");
        $display("Passed tests: %0d", passed_tests);
        $display("Failed tests: %0d", failed_tests);

        if (failed_tests == 0)
            $display("ALL ALU TESTS PASSED");
        else
            $display("SOME ALU TESTS FAILED");

        $finish;
    end

endmodule