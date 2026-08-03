`timescale 1ns/1ps

module counter_4bit_tb;

logic clk;
logic rst;
logic en;
logic [3:0] count;

counter_4bit dut (
    .clk(clk),
    .rst(rst),
    .en(en),
    .count(count)
);

integer pass = 0;
integer fail = 0;

/////////////////////////////////////////////////////
// Clock Generation
/////////////////////////////////////////////////////

initial begin
    clk = 0;
    forever #5 clk = ~clk;
end

/////////////////////////////////////////////////////
// VCD Dump & Monitor
/////////////////////////////////////////////////////

initial begin
    $dumpfile("counter_4bit.vcd");
    $dumpvars(0, counter_4bit_tb);
end

always @(posedge clk) begin
    $display("time=%0t rst=%b en=%b count=%b", $time, rst, en, count);
end

/////////////////////////////////////////////////////
// Test Sequence
/////////////////////////////////////////////////////

initial begin

    rst = 0;
    en  = 0;

    ////////////////////////////////
    // Reset Test
    ////////////////////////////////

    rst = 1;
    @(posedge clk);
    #1;

    if(count == 4'd0) begin
        $display("PASS : Reset");
        pass++;
    end
    else begin
        $display("FAIL : Reset Got=%0d", count);
        fail++;
    end

    rst = 0;

    ////////////////////////////////
    // Enable + Increment Test
    ////////////////////////////////

    en = 1;

    repeat(5) begin
        @(posedge clk);
    end
    #1;

    if(count == 4'd5) begin
        $display("PASS : Increment");
        pass++;
    end
    else begin
        $display("FAIL : Increment Expected=5 Got=%0d",count);
        fail++;
    end

    ////////////////////////////////
    // Hold Test
    ////////////////////////////////

    en = 0;

    @(posedge clk);
    #1;

    if(count == 4'd5) begin
        $display("PASS : Hold");
        pass++;
    end
    else begin
        $display("FAIL : Hold Got=%0d", count);
        fail++;
    end

    ////////////////////////////////
    // Wraparound Test
    ////////////////////////////////

    en = 1;

    repeat(11) begin
        @(posedge clk);
    end
    #1;

    if(count == 4'd0) begin
        $display("PASS : Wraparound");
        pass++;
    end
    else begin
        $display("FAIL : Wraparound Expected=0 Got=%0d",count);
        fail++;
    end

    ////////////////////////////////
    // Reset Priority Test
    ////////////////////////////////

    en  = 1;
    rst = 1;

    @(posedge clk);
    #1;

    if(count == 4'd0) begin
        $display("PASS : Reset Priority");
        pass++;
    end
    else begin
        $display("FAIL : Reset Priority Got=%0d", count);
        fail++;
    end

    rst = 0;

    ////////////////////////////////
    // Summary
    ////////////////////////////////

    $display("--------------------------------");
    $display("Tests Passed : %0d",pass);
    $display("Tests Failed : %0d",fail);
    $display("--------------------------------");

    if(fail == 0)
        $display("ALL TESTS PASSED");
    else
        $display("SOME TESTS FAILED");

    #20;
    $finish;

end

endmodule