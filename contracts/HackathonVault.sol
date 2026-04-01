// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title HackathonVault
 * @notice Capital vault tracking per-agent allocations.
 */
contract HackathonVault {
    address public owner;
    mapping(bytes32 => uint256) public allocatedCapital;
    uint256 public totalAllocated;

    event Deposited(address indexed from, uint256 amount);
    event CapitalAllocated(bytes32 indexed agentId, uint256 amount);
    event CapitalReleased(bytes32 indexed agentId, uint256 amount);
    event Withdrawn(address indexed to, uint256 amount);

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "HackathonVault: not owner");
        _;
    }

    function deposit() external payable {
        require(msg.value > 0, "HackathonVault: zero deposit");
        emit Deposited(msg.sender, msg.value);
    }

    receive() external payable {
        emit Deposited(msg.sender, msg.value);
    }

    function allocate(bytes32 agentId, uint256 amount) external onlyOwner {
        require(address(this).balance >= totalAllocated + amount, "HackathonVault: insufficient unallocated balance");
        allocatedCapital[agentId] += amount;
        totalAllocated += amount;
        emit CapitalAllocated(agentId, amount);
    }

    function release(bytes32 agentId, uint256 amount) external onlyOwner {
        require(allocatedCapital[agentId] >= amount, "HackathonVault: insufficient allocation");
        allocatedCapital[agentId] -= amount;
        totalAllocated -= amount;
        emit CapitalReleased(agentId, amount);
    }

    function withdraw(uint256 amount) external onlyOwner {
        uint256 unallocated = address(this).balance - totalAllocated;
        require(amount <= unallocated, "HackathonVault: would drain allocated capital");
        (bool ok, ) = owner.call{value: amount}("");
        require(ok, "HackathonVault: transfer failed");
        emit Withdrawn(owner, amount);
    }

    function getBalance(bytes32 agentId) external view returns (uint256) {
        return allocatedCapital[agentId];
    }

    function totalVaultBalance() external view returns (uint256) {
        return address(this).balance;
    }

    function unallocatedBalance() external view returns (uint256) {
        return address(this).balance - totalAllocated;
    }
}
